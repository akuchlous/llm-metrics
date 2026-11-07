"""Local publication runner: independent editorial and metrics release lanes.

Usage:
    python -m llm_metrics.publish_runner editorial --output DIR
        --site-url URL --publish-at YYYY-MM-DDTHH:MM:SSZ
        --state-dir DIR [--cost-ledger FILE] [--dry-run]
    python -m llm_metrics.publish_runner metrics --output DIR
        --site-url URL --now YYYY-MM-DDTHH:MM:SSZ --analytics FILE
        --data-source real --state-dir DIR [--allow-preliminary] [--dry-run]

Runs entirely on local files: it never contacts GCP, Cloudflare or a
provider, never runs Step 024 analytics, and never makes paid calls.
Deploying `--output` to a host is a separate, approval-gated action.

Lanes (they never block each other):
- **editorial**: publishes approved Q&A editions (`static_site` freeze) at an
  explicit time. Needs no analytics; it reuses the last *accepted* metrics
  dataset kept in `--state-dir`, so an editorial release never rolls metric
  pages back, and a missing or failed metrics refresh never blocks it.
- **metrics**: on the configured cadence (`publishing.json`:
  `metrics_frequency` daily | every_3_days | weekly at `metrics_run_at_utc`)
  rebuilds metric pages from a validated dataset, but only when a scheduled
  run is due, the dataset differs from the last accepted one, its window
  ended before the current UTC day began, and it is not a partial day
  (unless `--allow-preliminary`, which is an explicit manual approval).
  It never creates a Q&A edition or changes an answer. On any failure the
  previous output and accepted dataset stay as they were.

`publishing_enabled: false` in `publishing.json` is the emergency switch:
both lanes then do nothing. Every run appends one JSON line to
`<state-dir>/history.jsonl`.

Exit codes: 0 published or nothing to do (skip), 1 refused/failed, 2 usage.
"""

import argparse
import datetime
import hashlib
import json
import pathlib
import sys

from llm_metrics import static_site as ss

CONFIG_PATH = ss.CONTENT_DIR / "publishing.json"
FREQUENCIES = {"daily": 1, "every_3_days": 3, "weekly": 7}
# Anchor for multi-day cadences, so "every 3 days" is the same calendar
# days on every machine (UTC has no DST, so schedules never shift).
SCHEDULE_EPOCH = datetime.date(2026, 1, 5)  # a Monday
_UTC = datetime.timezone.utc
_TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
ACCEPTED_DATASET = "accepted-dataset.json"
STATE_FILE = "state.json"
HISTORY_FILE = "history.jsonl"


class RunnerError(Exception):
    """The run was refused; nothing was published."""


def parse_utc(text: str) -> datetime.datetime:
    try:
        return datetime.datetime.strptime(text, _TIME_FORMAT).replace(
            tzinfo=_UTC
        )
    except (TypeError, ValueError):
        raise RunnerError("Times must be UTC YYYY-MM-DDTHH:MM:SSZ.") from None


def load_config(path: pathlib.Path = CONFIG_PATH) -> dict:
    config = json.loads(pathlib.Path(path).read_text("utf-8"))
    if not isinstance(config.get("publishing_enabled"), bool):
        raise RunnerError("publishing_enabled must be true or false.")
    if config.get("metrics_frequency") not in FREQUENCIES:
        raise RunnerError(
            f"metrics_frequency must be one of {list(FREQUENCIES)}."
        )
    try:
        hour, minute = (int(x) for x in config["metrics_run_at_utc"].split(":"))
        datetime.time(hour, minute)
    except (KeyError, ValueError, TypeError, AttributeError):
        raise RunnerError("metrics_run_at_utc must be HH:MM (UTC).") from None
    return config


def latest_scheduled(now: datetime.datetime, config: dict) -> datetime.datetime:
    """The most recent scheduled metrics run time at or before `now`."""
    step = FREQUENCIES[config["metrics_frequency"]]
    hour, minute = (int(x) for x in config["metrics_run_at_utc"].split(":"))
    day = now.date()
    while True:
        candidate = datetime.datetime.combine(
            day, datetime.time(hour, minute), tzinfo=_UTC
        )
        if (day - SCHEDULE_EPOCH).days % step == 0 and candidate <= now:
            return candidate
        day -= datetime.timedelta(days=1)


def _read_state(state_dir: pathlib.Path) -> dict:
    path = state_dir / STATE_FILE
    return json.loads(path.read_text("utf-8")) if path.exists() else {}


def _write_json(path: pathlib.Path, value: dict) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _history(state_dir: pathlib.Path, entry: dict) -> None:
    with open(state_dir / HISTORY_FILE, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def _accepted_dataset(state_dir: pathlib.Path, state: dict):
    """(path, source) of the last accepted dataset, checked by hash."""
    path = state_dir / ACCEPTED_DATASET
    if not state.get("dataset_sha256"):
        return None, None
    if (
        not path.is_file()
        or hashlib.sha256(path.read_bytes()).hexdigest()
        != state["dataset_sha256"]
    ):
        raise RunnerError(
            "The accepted metrics dataset in the state directory is missing"
            " or changed; refusing to publish metric pages from it."
        )
    return path, state["data_source"]


def run_editorial(options) -> dict:
    state_dir = pathlib.Path(options.state_dir)
    state = _read_state(state_dir)
    dataset_path, source = _accepted_dataset(state_dir, state)
    if options.dry_run:
        _, archive_files, _, _ = ss.plan_site(
            ss.SiteConfig(options.site_url),
            None
            if dataset_path is None
            else ss.load_dataset(dataset_path, source, _expected()),
            pathlib.Path(options.content_dir),
            freeze_at=options.publish_at,
        )
        return {"result": "dry_run", "would_publish": sorted(archive_files)}
    _, _, published = ss.build(
        pathlib.Path(options.output),
        options.site_url,
        dataset_path,
        source,
        pathlib.Path(options.content_dir),
        freeze_at=options.publish_at,
        cost_ledger_path=None
        if options.cost_ledger is None
        else pathlib.Path(options.cost_ledger),
    )
    return {
        "result": "published" if published else "no_change",
        "published": published,
    }


def _expected() -> dict:
    _, pages, _ = ss.load_pages()
    return next(p for p in pages if p.kind == "metric").meta[
        "expected_population"
    ]


def run_metrics(options, config: dict) -> dict:
    state_dir = pathlib.Path(options.state_dir)
    state = _read_state(state_dir)
    now = parse_utc(options.now)
    due = latest_scheduled(now, config)
    last = state.get("last_metrics_run")
    if last is not None and parse_utc(last) >= due:
        return {
            "result": "skipped",
            "reason": "not_due",
            "next_after": ss_format(due),
        }
    dataset = ss.load_dataset(
        pathlib.Path(options.analytics), options.data_source, _expected()
    )
    if options.data_source != "real":
        raise RunnerError("Only a real dataset can refresh public metrics.")
    if dataset.sha256 == state.get("dataset_sha256"):
        result = {"result": "skipped", "reason": "unchanged_dataset"}
    else:
        population = dataset.summary["population"]
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if parse_utc(population["end_exclusive"]) > day_start:
            raise RunnerError(
                "Dataset window runs into the current UTC day; only complete"
                " days are published."
            )
        codes = {c["code"] for c in dataset.summary["caveats"]}
        if "partial_day" in codes and not options.allow_preliminary:
            raise RunnerError(
                "Dataset covers less than 24 hours; publishing it needs"
                " --allow-preliminary (an explicit manual approval)."
            )
        if options.dry_run:
            return {"result": "dry_run", "dataset_sha256": dataset.sha256}
        ss.build(
            pathlib.Path(options.output),
            options.site_url,
            pathlib.Path(options.analytics),
            options.data_source,
            pathlib.Path(options.content_dir),
        )
        (state_dir / ACCEPTED_DATASET).write_bytes(dataset.data)
        state.update(dataset_sha256=dataset.sha256, data_source="real")
        result = {"result": "published", "dataset_sha256": dataset.sha256}
    if not options.dry_run:
        state["last_metrics_run"] = ss_format(due)
        _write_json(state_dir / STATE_FILE, state)
    return result


def ss_format(moment: datetime.datetime) -> str:
    return moment.strftime(_TIME_FORMAT)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m llm_metrics.publish_runner", allow_abbrev=False
    )
    lanes = parser.add_subparsers(dest="lane", required=True)
    for name in ("editorial", "metrics"):
        lane = lanes.add_parser(name, allow_abbrev=False)
        lane.add_argument("--output", required=True)
        lane.add_argument("--site-url", required=True)
        lane.add_argument("--state-dir", required=True)
        lane.add_argument("--dry-run", action="store_true")
        lane.add_argument("--config", default=str(CONFIG_PATH))
        lane.add_argument("--content-dir", default=str(ss.CONTENT_DIR))
    editorial = lanes.choices["editorial"]
    editorial.add_argument("--publish-at", required=True)
    editorial.add_argument("--cost-ledger")
    metrics = lanes.choices["metrics"]
    metrics.add_argument("--now", required=True)
    metrics.add_argument("--analytics", required=True)
    metrics.add_argument(
        "--data-source", required=True, choices=ss.DATA_SOURCES
    )
    metrics.add_argument("--allow-preliminary", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    options = _parser().parse_args(argv)
    state_dir = pathlib.Path(options.state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    entry = {"lane": options.lane, "dry_run": options.dry_run}
    try:
        config = load_config(pathlib.Path(options.config))
        if not config["publishing_enabled"]:
            entry.update(result="skipped", reason="publishing_disabled")
        elif options.lane == "editorial":
            parse_utc(options.publish_at)
            entry.update(run_editorial(options))
        else:
            entry.update(run_metrics(options, config))
        code = 0
    except (RunnerError, ss.SiteError) as error:
        entry.update(result="refused", reason=str(error))
        code = 1
    if not options.dry_run:
        _history(state_dir, entry)
    print(json.dumps(entry, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
