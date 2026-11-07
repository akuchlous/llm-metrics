"""Synthetic local GCS mirror for `record_analytics` tests (Step 024).

Every value here is invented: attempt ids are sequential, provider request
ids say "synthetic", and the window (2026-01-05) predates every real pilot.
Records are labelled `prod` only because the analytics reads prod records;
none came from a provider.

Run `python -m tests.analytics_fixtures` to regenerate
`tests/fixtures/gcs_mirror/`; a test checks that the committed files equal
what this module builds, so the two cannot drift.

Scenario (scheduled-collector policy 2026-01-05T18:00Z, analysed to 20:00Z):

    18:00 success      18:15 success      18:30 provider_error
    18:45 success      19:00 success (no throughput, no provider request
    19:15 missing (no claim)               id, cached tokens unknown)
    19:30 claim without record             19:45 success

plus records the population filter must exclude: a one-off run at 17:10Z
(before the window), a different workload at 18:20Z, a `test` record, a
preflight probe, and a CSV backup outside the record prefix.
"""

import datetime
import pathlib
import sys

from llm_metrics import object_results as obj
from llm_metrics import scheduled_collector as sc

UTC = datetime.timezone.utc
FIXTURE_ROOT = pathlib.Path(__file__).parent / "fixtures" / "gcs_mirror"
PREFIX = "attempts"
POLICY_START = datetime.datetime(2026, 1, 5, 18, 0, tzinfo=UTC)
WINDOW_END = datetime.datetime(2026, 1, 5, 20, 0, tzinfo=UTC)
ORIGIN = ("gcp", "us-central1")
_TARGET = obj.ResultTarget("local-mirror", PREFIX)


def attempt_id(number: int) -> str:
    return f"{number:032x}"


def request_facts(number: int, **overrides) -> dict:
    input_tokens, output_tokens = 52, 100 + number % 50 * 3
    facts = {
        "provider": "openai",
        "model": "gpt-6-luna",
        "outcome": "success",
        "input_tokens": input_tokens,
        "requested_max_output_tokens": 300,
        "output_tokens": output_tokens,
        "input_price_per_1m": 0.1,
        "output_price_per_1m": 0.5,
        "input_cost": input_tokens * 0.1 / 1_000_000,
        "output_cost": output_tokens * 0.5 / 1_000_000,
        "total_cost": (input_tokens * 0.1 + output_tokens * 0.5) / 1_000_000,
        "failed_after_ms": None,
        "provider_request_id": f"synthetic-req-{number:04d}",
        "workload_id": "interactive-chat-v1",
        "origin_cloud": ORIGIN[0],
        "origin_region": ORIGIN[1],
        "cache_policy": "disabled",
        "cached_input_tokens": 0,
        "request_profile_id": "openai.gpt-6-luna.v1",
        "cached_input_price_per_1m": 0.01,
    }
    facts.update(overrides)
    return facts


_FAILURE = {
    "outcome": "provider_error",
    "input_tokens": None,
    "output_tokens": None,
    "input_cost": None,
    "output_cost": None,
    "total_cost": None,
    "cached_input_tokens": None,
    "failed_after_ms": 812.5,
    "provider_request_id": None,
}


def observations(
    ttft: float, total: float, tokens_per_s: float | None, model="gpt-6-luna"
):
    values = {"total_latency": total, "ttft": ttft}
    if tokens_per_s is not None:
        values["output_tokens_per_s"] = tokens_per_s
        values["output_chunks_per_s"] = tokens_per_s * 0.9
    return [
        {"provider": "openai", "model": model, "metric": m, "value": v}
        for m, v in values.items()
    ]


def record(number, recorded_at, facts, metric_results, environment="prod"):
    return obj.build_record(
        facts,
        metric_results,
        environment,
        attempt_id=attempt_id(number),
        recorded_at=recorded_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    )


# (slot minute after 18:00Z, attempt number, kind, ttft ms, total ms, tok/s)
SLOTS = (
    (0, 1, "success", 1650.25, 4290.5, 115.0),
    (15, 2, "success", 1420.0, 3980.75, 121.5),
    (30, 3, "provider_error", None, None, None),
    (45, 4, "success", 1880.5, 4710.0, 108.25),
    (60, 5, "success_sparse", 1510.0, 1690.0, None),
    (75, None, "missing", None, None, None),
    (90, 6, "claim_without_record", None, None, None),
    (105, 7, "success", 2210.75, 5120.25, 99.5),
)


def build_objects() -> dict[str, bytes]:
    """Object name (relative to the mirror root) -> exact bytes."""
    policy = sc.Policy(POLICY_START, POLICY_START + sc.WINDOW)
    objects = {}

    def put_record(new_record):
        objects[obj.object_name(_TARGET, new_record)] = obj.encode_record(
            new_record
        )

    for minute, number, kind, ttft, total, rate in SLOTS:
        slot = POLICY_START + datetime.timedelta(minutes=minute)
        if kind == "missing":
            continue
        claimed_at = slot + datetime.timedelta(seconds=4, microseconds=125000)
        objects[sc.claim_name(_TARGET, "prod", ORIGIN, slot)] = sc.claim_bytes(
            mode="prod",
            origin=ORIGIN,
            slot=slot,
            attempt_id=attempt_id(number),
            claimed_at=claimed_at,
            policy=policy,
        )
        if kind == "claim_without_record":
            continue
        if kind == "provider_error":
            recorded = claimed_at + datetime.timedelta(seconds=1)
            put_record(
                record(number, recorded, request_facts(number, **_FAILURE), [])
            )
            continue
        overrides = {}
        if kind == "success_sparse":
            overrides = {
                "provider_request_id": None,
                "cached_input_tokens": None,
            }
        recorded = claimed_at + datetime.timedelta(milliseconds=total + 250)
        put_record(
            record(
                number,
                recorded,
                request_facts(number, **overrides),
                observations(ttft, total, rate),
            )
        )

    # Excluded by the population filter (never claimed by the collector).
    one_off = datetime.datetime(2026, 1, 5, 17, 10, 3, 500000, tzinfo=UTC)
    put_record(
        record(
            90, one_off, request_facts(90), observations(1700.0, 4400.0, 112.0)
        )
    )
    other = datetime.datetime(2026, 1, 5, 18, 20, 1, tzinfo=UTC)
    put_record(
        record(
            91,
            other,
            request_facts(91, workload_id="long-output-v1"),
            observations(1300.0, 9000.0, 130.0),
        )
    )
    simulated = datetime.datetime(2026, 1, 5, 18, 5, tzinfo=UTC)
    put_record(
        record(
            92,
            simulated,
            request_facts(92),
            observations(5.0, 10.0, 1000.0),
            environment="test",
        )
    )
    objects[f"{PREFIX}/v1/preflight/2026-01-05/{attempt_id(93)}.json"] = (
        b'{"created_at":"2026-01-05T18:00:01.000000Z",'
        b'"kind":"llm-metrics.preflight.v1",'
        b'"probe_id":"0000000000000000000000000000005d"}'
    )
    objects["snapshots/018f/2026-01-04/requests.csv"] = (
        b"id,outcome\nsynthetic,success\n"
    )
    return dict(sorted(objects.items()))


def write_mirror(root: pathlib.Path) -> None:
    for name, data in build_objects().items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


if __name__ == "__main__":
    write_mirror(
        pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else FIXTURE_ROOT
    )
