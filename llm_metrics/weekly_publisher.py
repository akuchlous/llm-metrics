"""Weekly publication run: metric snapshots, cost updates, answer review.

Usage:
    python -m llm_metrics.weekly_publisher --now YYYY-MM-DDTHH:MM:SSZ
        --site-url URL --state-dir DIR --output DIR
        [--analytics FILE --series FILE] [--cost-ledger FILE]
        [--config FILE] [--content-dir DIR] [--dry-run]

Step 028. One run per week (`publishing.json`: `weekly_day`, default
sunday, at `weekly_run_at_utc`, default 02:00 UTC). It is publication
only: it never collects data, never calls a provider, GCP, Cloudflare or a
billing API, and never writes or approves answer prose. Deploying
`--output` is a separate step of the operator's (or the approved cloud
job's) script.

Inputs are local files that someone already reviewed: the candidate
analytics summary and per-slot series (Step 024/027c) and the private cost
ledger. The run decides, separately:

- **metrics**: `publish` a new dataset when it passes the production gate,
  its window ended before the scheduled run, it differs from every
  published metric snapshot, and no answer needs review; otherwise
  `no_change` (same dataset), `no_new_data` (none given) or `held` with
  the precise reason. Held or unchanged runs rebuild from the accepted
  copy in `--state-dir`, which must match the latest published snapshot,
  so metric pages never roll back or disappear.
- **costs**: `publish` a dated `/reports/<date>/project-costs` edition when
  the ledger's public content changed, `no_change`, `stale` (cut-off older
  than 8 days: disclosure, no edition) or `no_billing_input`.
- **answer review**: a machine-readable report (written to
  `<state-dir>/reviews/`) listing every approved answer linked to a metric
  and whether the new dataset needs an editor to review it. A
  dataset-based answer reviewed against another dataset is
  `review_needed` and holds the metrics update. Methodology answers state
  no measured values (enforced by `static_site`), so they need none.

Idempotency: each scheduled week is recorded in `<state-dir>/state.json`;
a retry of a week that already finished does nothing. Archive writes are
keyed by content (dataset SHA-256, cost content SHA-256, edition id), so a
crash between freezing and recording cannot create duplicates either.
Missed weeks are never caught up: only the latest scheduled week runs.

`publishing_enabled: false` stops every run. Exit codes: 0 done or nothing
to do, 1 refused (nothing written), 2 usage.
"""

# pylint: disable=protected-access

import argparse
import datetime
import hashlib
import json
import pathlib
import shutil
import sys

from llm_metrics import cost_ledger
from llm_metrics import publish_runner as pr
from llm_metrics import static_site as ss

DAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
STATE_FILE = "state.json"
HISTORY_FILE = "history.jsonl"
ACCEPTED_ANALYTICS = "accepted-analytics.json"
ACCEPTED_SERIES = "accepted-series.json"
_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_UTC = datetime.timezone.utc


class PublisherError(Exception):
    """The run was refused; nothing was written."""


def schedule(config: dict) -> tuple[int, datetime.time]:
    day = config.get("weekly_day", "sunday")
    if day not in DAYS:
        raise PublisherError(f"weekly_day must be one of {DAYS}.")
    try:
        hour, minute = (
            int(x) for x in config.get("weekly_run_at_utc", "02:00").split(":")
        )
        at = datetime.time(hour, minute)
    except (ValueError, TypeError, AttributeError):
        raise PublisherError("weekly_run_at_utc must be HH:MM.") from None
    return DAYS.index(day), at


def latest_week(now: datetime.datetime, config: dict) -> datetime.datetime:
    """The most recent scheduled weekly run at or before `now` (UTC)."""
    weekday, at = schedule(config)
    day = now.date() - datetime.timedelta(days=(now.weekday() - weekday) % 7)
    moment = datetime.datetime.combine(day, at, tzinfo=_UTC)
    if moment > now:
        moment -= datetime.timedelta(days=7)
    return moment


def _fmt(moment: datetime.datetime) -> str:
    return moment.strftime(_FORMAT)


def answer_review(questions, dataset_sha256: str | None) -> list[dict]:
    """One row per approved answer that is linked to a metric.

    `questions` are `static_site.Question`s. Nothing is approved or changed.
    """
    rows = []
    for question in questions:
        approved = [
            e for e in question.editions if e.page.meta["status"] == "approved"
        ]
        if not approved or not question.related_metrics:
            continue
        meta = approved[-1].page.meta
        row = {
            "question_id": question.question_id,
            "path": question.path,
            "answer_revision": meta["answer_revision"],
            "answer_basis": meta["answer_basis"],
            "reviewed_dataset_sha256": meta.get(
                "answer_reviewed_dataset_sha256"
            ),
            "candidate_dataset_sha256": dataset_sha256,
        }
        if meta["answer_basis"] == "methodology":
            row.update(
                status="not_needed",
                reason="Methodology answer: states no measured values;"
                " numbers come only from generated sections.",
            )
        elif dataset_sha256 is None or (
            meta.get("answer_reviewed_dataset_sha256") == dataset_sha256
        ):
            row.update(status="current", reason="Reviewed against this data.")
        else:
            row.update(
                status="review_needed",
                reason="The answer was reviewed against another dataset; an"
                " editor must confirm or revise it (a new edition).",
            )
        rows.append(row)
    return rows


def _published_datasets(archive_dir: pathlib.Path) -> list[str]:
    entries = ss.load_manifest(archive_dir).get("metric_snapshots", [])
    return [
        e["dataset_sha256"]
        for e in sorted(entries, key=lambda e: e["published_at"])
    ]


def _metrics(options, state_dir, archive_dir, scheduled, questions):
    """(decision dict, analytics path, series path) to build with."""
    published = _published_datasets(archive_dir)
    latest = published[-1] if published else None
    decision, review = None, []
    candidate = None
    if options.analytics is None:
        decision = {"decision": "no_new_data"}
    else:
        try:
            dataset = ss.load_dataset(
                pathlib.Path(options.analytics), "real", pr._expected()
            )
            dataset = ss.production_gate(dataset)
            if options.series is not None:
                ss.load_series(pathlib.Path(options.series), dataset)
        except ss.SiteError as error:
            decision = {"decision": "held", "reason": str(error)}
        else:
            end = dataset.summary["population"]["end_exclusive"]
            review = answer_review(questions, dataset.sha256)
            if dataset.sha256 == latest:
                decision = {"decision": "no_change"}
                candidate = dataset.sha256
            elif dataset.sha256 in published:
                decision = {
                    "decision": "held",
                    "reason": "Dataset is an older published snapshot.",
                }
            elif pr.parse_utc(end) > scheduled:
                decision = {
                    "decision": "held",
                    "reason": f"Window ends {end}, after this week's run.",
                }
            elif any(r["status"] == "review_needed" for r in review):
                decision = {
                    "decision": "held",
                    "reason": "Answer review needed before new numbers can"
                    " be published next to these answers.",
                }
            else:
                decision = {"decision": "publish"}
                candidate = dataset.sha256
            decision["dataset_sha256"] = dataset.sha256
            decision["window"] = [
                dataset.summary["population"]["start_inclusive"],
                end,
            ]
    if candidate is not None:
        return (
            decision,
            review,
            (
                pathlib.Path(options.analytics),
                None
                if options.series is None
                else pathlib.Path(options.series),
            ),
        )
    # Keep the current published numbers: rebuild from the accepted copy.
    if latest is None:
        return decision, review, (None, None)
    accepted = state_dir / ACCEPTED_ANALYTICS
    if (
        not accepted.is_file()
        or hashlib.sha256(accepted.read_bytes()).hexdigest() != latest
    ):
        raise PublisherError(
            "The accepted dataset in the state directory does not match the"
            " latest published snapshot; seed it with the published analytics"
            " (run once with --analytics of that dataset)."
        )
    series = state_dir / ACCEPTED_SERIES
    return decision, review, (accepted, series if series.is_file() else None)


def _costs(options, archive_dir, at):
    if options.cost_ledger is None:
        return {"decision": "no_billing_input"}, None
    try:
        ledger = cost_ledger.load(pathlib.Path(options.cost_ledger))
    except cost_ledger.LedgerError as error:
        raise PublisherError(f"Cost ledger refused: {error}") from None
    summary = cost_ledger.summarize(ledger.data)
    published = {
        e["content_sha256"]
        for e in ss.load_manifest(archive_dir).get("cost_editions", [])
    }
    if cost_ledger.stale(summary, at):
        decision = "stale"
    elif summary["content_sha256"] in published:
        decision = "no_change"
    else:
        decision = "publish"
    return {
        "decision": decision,
        "content_sha256": summary["content_sha256"],
        "reporting_cutoff": summary["reporting_cutoff"],
    }, pathlib.Path(options.cost_ledger)


def run(options) -> dict:
    now = pr.parse_utc(options.now)
    config = json.loads(pathlib.Path(options.config).read_text("utf-8"))
    if not config.get("publishing_enabled"):
        return {"result": "skipped", "reason": "publishing_disabled"}
    scheduled = latest_week(now, config)
    week = _fmt(scheduled)
    state_dir = pathlib.Path(options.state_dir)
    state_path = state_dir / STATE_FILE
    state = (
        json.loads(state_path.read_text("utf-8"))
        if state_path.exists()
        else {"weeks": {}}
    )
    if week in state["weeks"]:
        return {
            "result": "already_done",
            "week": week,
            "previous": state["weeks"][week]["result"],
        }
    content_dir = pathlib.Path(options.content_dir)
    archive_dir = content_dir / "archive"
    _, _, questions = ss.load_pages(content_dir)
    metrics, review, (analytics, series) = _metrics(
        options, state_dir, archive_dir, scheduled, questions
    )
    costs, ledger = _costs(options, archive_dir, options.now)
    record = {
        "week": week,
        "run_at": options.now,
        "metrics": metrics,
        "costs": costs,
        "answer_review": [
            {k: r[k] for k in ("question_id", "status")} for r in review
        ],
    }
    kwargs = {
        "freeze_at": options.now,
        "costs": None
        if ledger is None
        else cost_ledger.summarize(cost_ledger.load(ledger).data),
    }
    dataset = (
        None
        if analytics is None
        else ss.production_gate(
            ss.load_dataset(analytics, "real", pr._expected())
        )
    )
    files, archive_files, _, _ = ss.plan_site(
        ss.SiteConfig(options.site_url),
        dataset,
        content_dir,
        series=None if series is None else ss.load_series(series, dataset),
        **kwargs,
    )
    record["would_publish"] = sorted(
        "/" + n.removesuffix("/index.html") for n in archive_files
    )
    if options.dry_run:
        return {"result": "dry_run", **record}
    ss.check_output(pathlib.Path(options.output))
    _, _, published = ss.build(
        pathlib.Path(options.output),
        options.site_url,
        analytics,
        None if analytics is None else "real",
        content_dir,
        freeze_at=options.now,
        series_path=series,
        cost_ledger_path=ledger,
    )
    if analytics is not None and analytics.parent != state_dir:
        shutil.copyfile(analytics, state_dir / ACCEPTED_ANALYTICS)
        if series is not None:
            shutil.copyfile(series, state_dir / ACCEPTED_SERIES)
    reviews = state_dir / "reviews"
    reviews.mkdir(exist_ok=True)
    pr._write_json(
        reviews / f"{scheduled:%Y-%m-%d}.json",
        {"week": week, "rows": review},
    )
    record["published"] = published
    record["result"] = "published" if published else "no_change"
    state["weeks"][week] = {"result": record["result"], "run_at": options.now}
    pr._write_json(state_path, state)
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m llm_metrics.weekly_publisher", allow_abbrev=False
    )
    parser.add_argument("--now", required=True)
    parser.add_argument("--site-url", required=True)
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--analytics")
    parser.add_argument("--series")
    parser.add_argument("--cost-ledger")
    parser.add_argument("--config", default=str(pr.CONFIG_PATH))
    parser.add_argument("--content-dir", default=str(ss.CONTENT_DIR))
    parser.add_argument("--dry-run", action="store_true")
    options = parser.parse_args(argv)
    if options.series and not options.analytics:
        parser.error("--series needs --analytics")
    state_dir = pathlib.Path(options.state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    try:
        entry = run(options)
        code = 0
    except (PublisherError, pr.RunnerError, ss.SiteError) as error:
        entry = {"result": "refused", "reason": str(error)}
        code = 1
    entry = {"dry_run": options.dry_run, **entry}
    if not options.dry_run:
        with open(state_dir / HISTORY_FILE, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
    print(json.dumps(entry, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
