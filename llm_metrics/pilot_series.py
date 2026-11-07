"""Per-slot time series of one collector pilot, for charts (Step 027c).

Usage:
    python -m llm_metrics.pilot_series --input MIRROR --output FILE
        --start POLICY_START --end YYYY-MM-DDTHH:MM:SSZ [--prefix attempts]

Builds schema `llm-metrics.pilot-series.v1` from the same local mirror and
the same validation as Step 024 `record_analytics` (the scheduled
collector's fixed scope: openai, gpt-6-luna, openai.gpt-6-luna.v1,
interactive-chat-v1, gcp/us-central1). It never contacts GCP or a provider.

One row per policy slot (always 96), in order:
- `success`: the slot's one request succeeded; its own TTFT, total latency
  and output tokens/s (per-request observations, not averages), rounded to
  0.1 ms and 0.1 tokens/s for display; a throughput the record did not
  report is null, never 0.
- `failure`: the request was recorded as failed, with its category; no
  latency value exists.
- `missing` (no claim) or `claim_without_record`: a due slot without a
  record.
- `not_due`: the slot begins at or after `end` (the data cutoff).

Only slot times, states, categories and the rounded values are written: no
attempt ids, object names, provider ids, prompts or responses. The file
carries the record manifest SHA-256 of the analytics summary over the same
records, so a page can check that both describe the same evidence.
"""

import argparse
import hashlib
import json
import pathlib
import sys

from llm_metrics import collector_audit
from llm_metrics import object_results
from llm_metrics import outcomes
from llm_metrics import record_analytics as ra
from llm_metrics import scheduled_collector as sc

SCHEMA_VERSION = "llm-metrics.pilot-series.v1"
STATES = ("success", "failure", "missing", "claim_without_record", "not_due")
_VALUES = {
    "ttft_ms": "ttft",
    "total_latency_ms": "total_latency",
    "output_tokens_per_s": "output_tokens_per_s",
}


def _population(start, end, region="us-central1") -> ra.Population:
    return ra.Population(
        provider=sc.TARGET.provider,
        model=sc.TARGET.model,
        request_profile_id=sc.TARGET.profile_id,
        workload_id=sc.WORKLOAD_ID,
        origin_cloud=sc.ORIGIN_CLOUD,
        origin_region=region,
        start=start,
        end=end,
    )


def _claims(root: pathlib.Path, prefix: str, population, policy) -> dict:
    """slot -> claimed attempt id, read from the mirror's claim objects."""
    store = collector_audit.LocalDirStore(root)
    target = object_results.ResultTarget("local-mirror", prefix)
    origin = (population.origin_cloud, population.origin_region)
    claims = {}
    for slot in policy.slots():
        name = sc.claim_name(target, "prod", origin, slot)
        raw = store.read(target.bucket, name)
        if raw is None:
            continue
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        if data.get("kind") == sc.CLAIM_KIND:
            claims[slot] = data["attempt_id"]
    return claims


def _value(record: dict, metric: str, digits: int = 1):
    for observation in record["observations"]:
        if observation["metric"] == metric:
            return round(observation["value"], digits)
    return None


def build(
    root: pathlib.Path,
    prefix: str,
    population: ra.Population,
) -> bytes:
    """Validates like `record_analytics` and returns canonical series bytes.

    Raises:
        ra.AnalyticsInputError: Any validation failure (nothing written).
    """
    selection = ra.load_records(root, prefix, population)
    if not selection.records:
        raise ra.AnalyticsInputError("No records match the population.")
    # Same claim/record agreement checks as the analytics summary.
    slots = ra.slot_evidence(
        root, prefix, population, population.start, selection
    )
    policy = sc.Policy(population.start, population.start + sc.WINDOW)
    claims = _claims(root, prefix, population, policy)
    by_id = {r.record["attempt_id"]: r.record for r in selection.records}
    rows = []
    for slot in policy.slots():
        row = {"slot": sc.format_utc(slot)}
        attempt_id = claims.get(slot)
        record = by_id.get(attempt_id)
        if slot >= population.end:
            row["state"] = "not_due"
        elif attempt_id is None:
            row["state"] = "missing"
        elif record is None:
            row["state"] = "claim_without_record"
        elif record["request"]["outcome"] == outcomes.SUCCESS:
            row["state"] = "success"
            for key, metric in _VALUES.items():
                row[key] = _value(record, metric)
        else:
            row["state"] = "failure"
            row["failure_category"] = record["request"]["outcome"]
        rows.append(row)
    counts = {state: sum(r["state"] == state for r in rows) for state in STATES}
    expected = {
        "success": slots["states"]["recorded_success"],
        "failure": slots["states"]["recorded_failure"],
        "missing": slots["states"]["missing"],
        "claim_without_record": slots["states"]["claim_without_record"],
    }
    if any(counts[k] != v for k, v in expected.items()):
        raise ra.AnalyticsInputError(
            "Per-slot states disagree with the collector audit."
        )
    series = {
        "schema_version": SCHEMA_VERSION,
        "population": population.as_dict(),
        "policy": slots["policy"],
        "cutoff": sc.format_utc(population.end),
        "due_slots": slots["expected_slots"],
        "counts": counts,
        "rounding": {"ms": 0.1, "tokens/s": 0.1},
        "record_manifest_sha256": hashlib.sha256(
            ra.manifest(selection.records).encode("utf-8")
        ).hexdigest(),
        "slots": rows,
    }
    return ra.encode_summary(series)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m llm_metrics.pilot_series", allow_abbrev=False
    )
    parser.add_argument("--input", required=True, help="local mirror root")
    parser.add_argument("--output", required=True)
    utc = ra._utc_argument  # pylint: disable=protected-access
    parser.add_argument("--start", required=True, type=utc)
    parser.add_argument("--end", required=True, type=utc)
    parser.add_argument("--prefix", default="attempts")
    parser.add_argument("--region", default="us-central1")
    options = parser.parse_args(argv)
    try:
        population = _population(options.start, options.end, options.region)
        data = build(pathlib.Path(options.input), options.prefix, population)
        created = ra.write_summary(
            pathlib.Path(options.output),
            data,
            input_root=pathlib.Path(options.input),
        )
    except (ra.AnalyticsInputError, ra.AnalyticsOutputError) as error:
        print(f"Error: {error} Nothing written.", file=sys.stderr)
        return 1
    print(
        f"{'Wrote' if created else 'Unchanged'} {options.output}:"
        f" sha256 {hashlib.sha256(data).hexdigest()}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
