"""Offline, read-only analytics over a local mirror of immutable GCS records.

Usage:
    python -m llm_metrics.record_analytics --input MIRROR --output FILE
        --provider P --model M --profile PROFILE --workload W
        --origin CLOUD/REGION --start YYYY-MM-DDTHH:MM:SSZ
        --end YYYY-MM-DDTHH:MM:SSZ [--prefix attempts]
        [--collector-policy-start YYYY-MM-DDTHH:MM:SSZ]

`MIRROR` is a local copy of the results bucket, for example made by an
operator with
    gcloud storage cp -r gs://BUCKET/attempts/v1 MIRROR/attempts/
This module never contacts GCP, OpenAI or any database: it reads files under
`MIRROR/<prefix>/v1/requests/prod/` only and writes exactly one local file.

Owns: selecting one explicitly filtered population of real (`prod`)
`llm-metrics.attempt.v1` records, validating every candidate file with
`object_results.decode_record`, computing a versioned summary (schema
`llm-metrics.analytics.v1`), and writing it create-only and atomically.
It does not own the record schema (`object_results`), percentile arithmetic
(`percentiles`), outcome vocabulary (`outcomes`), or slot/claim semantics
(`collector_audit`); it reuses them. It is independent of the SQL-backed
`analytics`/`dashboard` path and imports no web framework.

Population rules:
- Only `prod` records are read; `test` (simulated) records live under a
  different directory and are never opened. CSV backups (`snapshots/`, Steps
  018f/020) are not records and are never read; importing them would need a
  separate, explicit step.
- Records are selected by exact provider, model, request profile, workload,
  origin cloud and region, and `start <= recorded_at < end` (UTC). A record
  with the selected profile but a different provider/model is a mixed
  population and fails the run instead of being silently dropped.
- Reliability counts every selected attempt; metric distributions use
  successful observations only (failures have none, so no latency is ever a
  fabricated 0). A failed attempt's cost is unknown and counted, never $0.
- Records alone cannot show scheduled slots that produced no record. Slot
  completeness is reported only when `--collector-policy-start` is given,
  from the claims in the same mirror via `collector_audit.audit`; otherwise
  it is null.

Fail-closed: any unreadable, malformed, non-canonical, misplaced, oversized,
symlinked or unexpected entry in the scanned directories, a duplicate
provider request id, inconsistent slot evidence, or zero selected records
stops the run before anything is written.

Exit codes: 0 summary written (or the identical file already existed), 1
invalid input or output collision (nothing written), 2 bad arguments.
"""

import argparse
import collections
import dataclasses
import datetime
import hashlib
import json
import math
import os
import pathlib
import re
import sys
import tempfile

from llm_metrics import collector_audit
from llm_metrics import latency
from llm_metrics import object_results
from llm_metrics import outcomes
from llm_metrics import percentiles
from llm_metrics import scheduled_collector as sc

SCHEMA_VERSION = "llm-metrics.analytics.v1"
ENVIRONMENT = "prod"
SUMMARY_PERCENTILES = (50, 95)

# Bounds on what one run will read. A v1 record is well under 2 KiB; the
# tree bound covers records, claims and preflight probes of many windows.
MAX_RECORD_BYTES = 64 * 1024
MAX_TREE_ENTRIES = 200_000

# Below this many successes nearest-rank p95 is the sample maximum
# (ceil(0.95 * n) == n for n <= 19).
_P95_DISTINCT_FROM_MAX = 20
_STABLE_PERCENTILE_SAMPLE = 100

_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RECORD_FILE_RE = re.compile(r"^[0-9a-f]{32}\.json$")
_UTC = datetime.timezone.utc
_RECORD_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


class AnalyticsInputError(ValueError):
    """The input is missing, unsafe or invalid. Nothing was written.

    Messages name paths and field names only, never record values.
    """


class AnalyticsOutputError(Exception):
    """The output path is unsafe or holds different content. Not written."""


@dataclasses.dataclass(frozen=True)
class Population:
    """The exact population a summary describes. Every field is required.

    `start` is inclusive and `end` exclusive; both are aware UTC datetimes.
    """

    provider: str
    model: str
    request_profile_id: str
    workload_id: str
    origin_cloud: str
    origin_region: str
    start: datetime.datetime
    end: datetime.datetime

    def __post_init__(self):
        for field in (
            "provider",
            "model",
            "request_profile_id",
            "workload_id",
            "origin_cloud",
            "origin_region",
        ):
            value = getattr(self, field)
            if not isinstance(value, str) or not value:
                raise AnalyticsInputError(
                    f"{field} must be a non-empty string."
                )
        # Same naming rule as `targets.RequestProfile`: a profile belongs to
        # exactly one provider/model, so a mismatched filter selects nothing
        # by accident rather than by intent.
        if not self.request_profile_id.startswith(
            f"{self.provider}.{self.model}.v"
        ):
            raise AnalyticsInputError(
                "request_profile_id does not belong to provider/model."
            )
        for moment in (self.start, self.end):
            if moment.tzinfo is None or moment.utcoffset():
                raise AnalyticsInputError("start and end must be UTC.")
        if self.start >= self.end:
            raise AnalyticsInputError("start must be before end.")

    def as_dict(self) -> dict:
        return {
            "environment": ENVIRONMENT,
            "provider": self.provider,
            "model": self.model,
            "request_profile_id": self.request_profile_id,
            "workload_id": self.workload_id,
            "origin_cloud": self.origin_cloud,
            "origin_region": self.origin_region,
            "start_inclusive": sc.format_utc(self.start),
            "end_exclusive": sc.format_utc(self.end),
        }


@dataclasses.dataclass(frozen=True)
class LoadedRecord:
    """One validated record and the evidence that identifies its bytes.

    Attributes:
        object_name: Its bucket object name (`<prefix>/v1/requests/...`).
        sha256: Hex SHA-256 of the exact file bytes.
        record: The decoded, validated v1 record.
    """

    object_name: str
    sha256: str
    record: dict


@dataclasses.dataclass(frozen=True)
class Selection:
    """Records selected for a population, plus what the scan excluded."""

    records: tuple[LoadedRecord, ...]
    scanned: int
    excluded: dict[str, int]


def parse_record_time(recorded_at: str) -> datetime.datetime:
    return datetime.datetime.strptime(recorded_at, _RECORD_TIME_FORMAT).replace(
        tzinfo=_UTC
    )


def _check_tree(prefix_dir: pathlib.Path) -> None:
    """Rejects symlinks and oversized trees anywhere under the prefix.

    A symlink could point a "record" at a file outside the mirror, or make
    the same bytes appear under two names; neither belongs in evidence.
    """
    entries = 0
    for directory, subdirs, files in os.walk(prefix_dir, followlinks=False):
        for name in subdirs + files:
            entries += 1
            if entries > MAX_TREE_ENTRIES:
                raise AnalyticsInputError(
                    f"Input has more than {MAX_TREE_ENTRIES} entries."
                )
            path = os.path.join(directory, name)
            if os.path.islink(path):
                raise AnalyticsInputError(
                    "Input contains a symlink:"
                    f" {os.path.relpath(path, prefix_dir)}"
                )


def _real_directory(path: pathlib.Path, label: str) -> None:
    if path.is_symlink() or not path.is_dir():
        raise AnalyticsInputError(f"{label} is not a directory: {path}")


def _days(population: Population) -> list[str]:
    """UTC dates whose directories can hold records of [start, end)."""
    last = population.end - datetime.timedelta(microseconds=1)
    day = population.start.date()
    days = []
    while day <= last.date():
        days.append(day.isoformat())
        day += datetime.timedelta(days=1)
    return days


def _exclusion(record: dict, population: Population) -> str | None:
    """Returns why a valid prod record is outside the population, or None.

    Raises:
        AnalyticsInputError: The record has the selected profile but a
            different provider/model (a mixed population).
    """
    facts = record["request"]
    if facts["request_profile_id"] == population.request_profile_id and (
        facts["provider"],
        facts["model"],
    ) != (population.provider, population.model):
        raise AnalyticsInputError(
            "Mixed population: a record with the selected profile has a"
            " different provider/model."
        )
    moment = parse_record_time(record["recorded_at"])
    if not population.start <= moment < population.end:
        return "outside_time_window"
    if (facts["provider"], facts["model"], facts["request_profile_id"]) != (
        population.provider,
        population.model,
        population.request_profile_id,
    ):
        return "other_profile"
    if facts["workload_id"] != population.workload_id:
        return "other_workload"
    if (facts["origin_cloud"], facts["origin_region"]) != (
        population.origin_cloud,
        population.origin_region,
    ):
        return "other_origin"
    return None


def load_records(
    root: pathlib.Path, prefix: str, population: Population
) -> Selection:
    """Loads and validates the prod records of a population from a mirror.

    Every file in the scanned day directories is decoded and validated, even
    when it ends up excluded, so a damaged mirror never yields a plausible
    partial summary.

    Args:
        root: The mirror root (the bucket's contents).
        prefix: Record prefix inside the bucket, e.g. "attempts".
        population: The exact population to select.

    Returns:
        The selected records sorted by (recorded_at, attempt_id), the number
        of files scanned, and exclusion counts by reason.

    Raises:
        AnalyticsInputError: Unsafe or invalid input (see module docstring).
    """
    try:
        object_results.ResultTarget("local-mirror", prefix)
    except object_results.TargetConfigError as error:
        raise AnalyticsInputError(str(error)) from None
    root = pathlib.Path(root)
    _real_directory(root, "Input")
    prefix_dir = root / prefix
    requests_dir = prefix_dir / "v1" / "requests" / ENVIRONMENT
    # Symlinks below the prefix are rejected by _check_tree.
    for directory in (prefix_dir, requests_dir):
        _real_directory(directory, "Records path")
    _check_tree(prefix_dir)
    for entry in requests_dir.iterdir():
        if not entry.is_dir() or not _DAY_RE.match(entry.name):
            raise AnalyticsInputError(
                f"Unexpected entry in the records directory: {entry.name}"
            )

    selected, excluded, scanned = [], collections.Counter(), 0
    provider_request_ids = set()
    for day in _days(population):
        day_dir = requests_dir / day
        if not day_dir.exists():
            continue
        for path in sorted(day_dir.iterdir()):
            name = f"{prefix}/v1/requests/{ENVIRONMENT}/{day}/{path.name}"
            if not path.is_file() or not _RECORD_FILE_RE.match(path.name):
                raise AnalyticsInputError(f"Not a record file: {name}")
            if path.stat().st_size > MAX_RECORD_BYTES:
                raise AnalyticsInputError(f"Record file too large: {name}")
            data = path.read_bytes()
            scanned += 1
            try:
                record = object_results.decode_record(data, expected_name=name)
            except object_results.InvalidRecordError as error:
                raise AnalyticsInputError(
                    f"Invalid record {name}: {error}"
                ) from None
            reason = _exclusion(record, population)
            if reason is not None:
                excluded[reason] += 1
                continue
            request_id = record["request"]["provider_request_id"]
            if request_id is not None:
                # Two records of one provider request would count a single
                # measurement twice. The id itself is never echoed.
                if request_id in provider_request_ids:
                    raise AnalyticsInputError(
                        f"Duplicate provider request id in {name}."
                    )
                provider_request_ids.add(request_id)
            selected.append(
                LoadedRecord(name, hashlib.sha256(data).hexdigest(), record)
            )
    selected.sort(
        key=lambda r: (r.record["recorded_at"], r.record["attempt_id"])
    )
    return Selection(tuple(selected), scanned, dict(sorted(excluded.items())))


def slot_evidence(
    root: pathlib.Path,
    prefix: str,
    population: Population,
    policy_start: datetime.datetime,
    selection: Selection,
) -> dict:
    """Slot completeness from the collector's claims in the same mirror.

    Delegates slot classification to `collector_audit.audit` and then
    requires the claims and the selected records to agree exactly: every
    selected record is claimed by a begun slot, and the audit's recorded
    success/failure counts equal the selection's. Anything else means the
    window mixes populations or cuts a slot's record off, and fails.

    Raises:
        AnalyticsInputError: Out-of-scope population, invalid policy,
            invalid claims or records, or claims and records disagree.
    """
    scope = (
        population.provider,
        population.model,
        population.request_profile_id,
        population.workload_id,
        population.origin_cloud,
    )
    if scope != (
        sc.TARGET.provider,
        sc.TARGET.model,
        sc.TARGET.profile_id,
        sc.WORKLOAD_ID,
        sc.ORIGIN_CLOUD,
    ):
        raise AnalyticsInputError(
            "Slot evidence exists only for the scheduled collector's scope."
        )
    try:
        policy = sc.Policy(policy_start, policy_start + sc.WINDOW)
    except sc.CollectorConfigError as error:
        raise AnalyticsInputError(str(error)) from None
    if population.start != policy.start:
        raise AnalyticsInputError(
            "With slot evidence, --start must equal the policy start."
        )
    if population.end > policy.expires + sc.LATE_LIMIT:
        raise AnalyticsInputError(
            "With slot evidence, --end must not pass the policy expiry plus"
            " the late limit."
        )
    report = collector_audit.audit(
        collector_audit.LocalDirStore(root),
        object_results.ResultTarget("local-mirror", prefix),
        policy,
        mode="prod",
        origin=(population.origin_cloud, population.origin_region),
        # A slot beginning exactly at `end` is outside [start, end).
        now=population.end - datetime.timedelta(microseconds=1),
    )
    if report["invalid_records"] or report["claims_outside_policy"]:
        raise AnalyticsInputError(
            "Slot evidence has invalid records or claims outside the policy."
        )
    selected_ids = {r.record["attempt_id"] for r in selection.records}
    if selected_ids & set(report["records_without_claim"]):
        raise AnalyticsInputError(
            "Mixed population: selected records include records no slot"
            " claim accounts for."
        )
    states = {
        state: report["states"].get(state, 0)
        for state in (
            "recorded_success",
            "recorded_failure",
            "claim_without_record",
            "missing",
        )
    }
    successes = sum(
        r.record["request"]["outcome"] == outcomes.SUCCESS
        for r in selection.records
    )
    failure_ids = {
        p["attempt_id"]
        for p in report["problems"]
        if p["state"] == "recorded_failure"
    }
    if (
        states["recorded_success"] != successes
        or states["recorded_failure"] != len(selection.records) - successes
        or not failure_ids <= selected_ids
    ):
        raise AnalyticsInputError(
            "Slot evidence and selected records disagree (a slot's record"
            " falls outside the window, or records are out of scope)."
        )
    return {
        "source": "collector claims in the same mirror (collector_audit)",
        "policy": report["policy"],
        "audited_until": report["audited_until"],
        "expected_slots": report["expected_slots_so_far"],
        "states": states,
        "problems": report["problems"],
    }


def _metric_summary(metric: str, successes: list[dict]) -> dict:
    """Nearest-rank summary of one metric over successful records only.

    Keys are fixed whatever the data, with null for "no value"; a metric a
    success did not record (an undefined throughput) is counted, not 0.
    """
    points = [
        (record["recorded_at"], record["attempt_id"], observation["value"])
        for record in successes
        for observation in record["observations"]
        if observation["metric"] == metric
    ]
    values = [value for _, _, value in points]
    summary = {
        "unit": latency.METRICS[metric][1],
        "count": len(values),
        "successes_without_value": len(successes) - len(values),
        "min": min(values) if values else None,
        "max": max(values) if values else None,
        "latest": None,
    }
    for p in SUMMARY_PERCENTILES:
        summary[f"p{p}"] = percentiles.percentile(values, p) if values else None
    if points:
        recorded_at, attempt_id, value = points[-1]
        summary["latest"] = {
            "value": value,
            "recorded_at": recorded_at,
            "attempt_id": attempt_id,
        }
    return summary


def _known_sum(values: list) -> float | int | None:
    """Sum of the known values, or None when none is known (never 0)."""
    known = [value for value in values if value is not None]
    if not known:
        return None
    if all(isinstance(value, int) for value in known):
        return sum(known)
    # fsum is exact up to the final rounding, so the total does not depend
    # on summation order.
    return math.fsum(known)


def _caveats(
    population: Population,
    attempts: int,
    successes: list[dict],
    metrics: dict,
    slots: dict | None,
) -> list[dict]:
    caveats = [
        {
            "code": "observed_success_rate",
            "detail": "Success rate is what this runner observed from one"
            " origin and workload, not provider uptime.",
        }
    ]
    if slots is None:
        caveats.append({
            "code": "no_slot_evidence",
            "detail": "Records alone cannot show scheduled slots that"
            " produced no record; slot completeness is not reported.",
        })  # fmt: skip
    elif slots["states"]["missing"] or slots["states"]["claim_without_record"]:
        caveats.append({
            "code": "slots_without_records",
            "detail": "Some begun slots have no record; they are not in the"
            " attempt or reliability counts.",
        })  # fmt: skip
    if population.end - population.start < datetime.timedelta(hours=24):
        caveats.append({
            "code": "partial_day",
            "detail": "The window is shorter than 24 hours and may not"
            " cover daily traffic patterns.",
        })  # fmt: skip
    if len(successes) < _STABLE_PERCENTILE_SAMPLE:
        caveats.append({
            "code": "small_sample",
            "detail": f"Fewer than {_STABLE_PERCENTILE_SAMPLE} successful"
            " attempts; percentiles are unstable estimates.",
        })  # fmt: skip
    if 0 < len(successes) < _P95_DISTINCT_FROM_MAX:
        caveats.append({
            "code": "p95_is_sample_max",
            "detail": "With fewer than 20 successes, nearest-rank p95 equals"
            " the largest observed value.",
        })  # fmt: skip
    if attempts > len(successes):
        caveats.append({
            "code": "failed_cost_unknown",
            "detail": "Failed attempts have unknown cost and tokens; they"
            " are counted, not added as zero.",
        })  # fmt: skip
    if any(m["successes_without_value"] for m in metrics.values()):
        caveats.append({
            "code": "throughput_undefined_for_some",
            "detail": "Some successes have no throughput value (undefined"
            " for very short streams); those are counted, not zero.",
        })  # fmt: skip
    return caveats


def manifest(records: tuple[LoadedRecord, ...]) -> str:
    """`sha256sum`-format manifest of the evidence (one line per record).

    `sha256sum -c` run from the mirror root verifies it against the files.
    """
    return "".join(f"{r.sha256}  {r.object_name}\n" for r in records)


def summarize(
    selection: Selection, population: Population, slots: dict | None = None
) -> dict:
    """Builds the `llm-metrics.analytics.v1` summary of a selection.

    Pure and deterministic: no wall-clock fields, sorted inputs, canonical
    order. All costs are USD; latencies ms; throughput per second.

    Raises:
        AnalyticsInputError: When no record was selected (an empty summary
            would look like a measurement of nothing).
    """
    if not selection.records:
        raise AnalyticsInputError(
            "No records match the population; nothing written."
        )
    records = [loaded.record for loaded in selection.records]
    successes = [
        r for r in records if r["request"]["outcome"] == outcomes.SUCCESS
    ]
    reliability = outcomes.success_rate(
        collections.Counter(r["request"]["outcome"] for r in records)
    )
    metrics = {
        metric: _metric_summary(metric, successes) for metric in latency.METRICS
    }
    facts = [r["request"] for r in successes]
    all_facts = [r["request"] for r in records]
    return {
        "schema_version": SCHEMA_VERSION,
        "record_schema_version": object_results.SCHEMA_VERSION,
        "population": population.as_dict(),
        "source": {
            "csv_backups_included": False,
            "files_scanned": selection.scanned,
            "excluded_by_filter": selection.excluded,
        },
        "data_window": {
            "earliest_recorded_at": records[0]["recorded_at"],
            "latest_recorded_at": records[-1]["recorded_at"],
        },
        "reliability": reliability,
        "metrics": metrics,
        "cost_usd": {
            "known_total_cost": _known_sum([f["total_cost"] for f in facts]),
            "known_input_cost": _known_sum([f["input_cost"] for f in facts]),
            "known_output_cost": _known_sum([f["output_cost"] for f in facts]),
            "priced_successes": len(facts),
            "failed_attempts_cost_unknown": len(records) - len(successes),
        },
        "tokens": {
            "input_tokens": _known_sum([f["input_tokens"] for f in facts]),
            "output_tokens": _known_sum([f["output_tokens"] for f in facts]),
            "cached_input_tokens_known": _known_sum(
                [f["cached_input_tokens"] for f in facts]
            ),
            "cached_input_tokens_unknown_count": sum(
                f["cached_input_tokens"] is None for f in facts
            ),
        },
        "request_settings": {
            "cache_policies": sorted({f["cache_policy"] for f in all_facts}),
            "requested_max_output_tokens": sorted(
                {f["requested_max_output_tokens"] for f in all_facts}
            ),
            "prices_per_1m": sorted(
                (
                    {"input": i, "output": o, "cached_input": c}
                    for i, o, c in {
                        (
                            f["input_price_per_1m"],
                            f["output_price_per_1m"],
                            f["cached_input_price_per_1m"],
                        )
                        for f in all_facts
                    }
                ),
                key=lambda price: json.dumps(price, sort_keys=True),
            ),
        },
        "provenance": {
            "records_without_provider_request_id": sum(
                f["provider_request_id"] is None for f in all_facts
            ),
        },
        "slot_completeness": slots,
        "caveats": _caveats(
            population, len(records), successes, metrics, slots
        ),
        "evidence": {
            "record_count": len(selection.records),
            "manifest_sha256": hashlib.sha256(
                manifest(selection.records).encode("utf-8")
            ).hexdigest(),
            "records": [
                {
                    "object_name": loaded.object_name,
                    "attempt_id": loaded.record["attempt_id"],
                    "recorded_at": loaded.record["recorded_at"],
                    "outcome": loaded.record["request"]["outcome"],
                    "sha256": loaded.sha256,
                }
                for loaded in selection.records
            ],
        },
    }


def encode_summary(summary: dict) -> bytes:
    """Canonical bytes: UTF-8, sorted keys, compact, no NaN/Infinity.

    Raises:
        AnalyticsInputError: If a value is not finite JSON.
    """
    try:
        return json.dumps(
            summary,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except ValueError:
        raise AnalyticsInputError("Summary has a non-finite number.") from None


def write_summary(
    path: pathlib.Path, data: bytes, *, input_root: pathlib.Path
) -> bool:
    """Writes `data` create-only and atomically; never overwrites.

    The bytes go to a temporary file in the destination directory, are
    fsynced, then hard-linked to `path` (atomic, and refused by the OS if
    `path` exists), so a reader sees either no file or the complete one.

    Returns:
        True if created; False if `path` already held identical bytes.

    Raises:
        AnalyticsOutputError: Unsafe path (symlink, inside the input mirror,
            missing directory) or an existing file with different bytes.
    """
    path = pathlib.Path(path)
    if path.is_symlink():
        raise AnalyticsOutputError(f"Output is a symlink: {path}")
    parent = path.parent.resolve()
    if not parent.is_dir():
        raise AnalyticsOutputError(f"Output directory does not exist: {parent}")
    destination = parent / path.name
    if destination.is_relative_to(pathlib.Path(input_root).resolve()):
        raise AnalyticsOutputError(
            "Output must not be inside the input mirror."
        )

    def existing_matches() -> bool:
        if not destination.is_file() or destination.is_symlink():
            raise AnalyticsOutputError(f"Output exists: {destination}")
        if destination.read_bytes() != data:
            raise AnalyticsOutputError(
                f"Output exists with different content: {destination}"
            )
        return True

    if destination.exists() or destination.is_symlink():
        return not existing_matches()
    descriptor, temporary = tempfile.mkstemp(
        dir=parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError:
            return not existing_matches()
    finally:
        os.unlink(temporary)
    directory = os.open(parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return True


def build(
    root: pathlib.Path,
    prefix: str,
    population: Population,
    policy_start: datetime.datetime | None = None,
) -> bytes:
    """Loads, validates and summarizes; returns the canonical summary bytes."""
    selection = load_records(root, prefix, population)
    if not selection.records:
        raise AnalyticsInputError(
            "No records match the population; nothing written."
        )
    slots = None
    if policy_start is not None:
        slots = slot_evidence(root, prefix, population, policy_start, selection)
    return encode_summary(summarize(selection, population, slots))


def _utc_argument(text: str) -> datetime.datetime:
    try:
        return sc.parse_utc(text, "time")
    except sc.CollectorConfigError:
        raise argparse.ArgumentTypeError(
            "must be UTC 'YYYY-MM-DDTHH:MM:SSZ'"
        ) from None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m llm_metrics.record_analytics",
        description="Offline analytics summary from a local mirror of"
        " immutable prod records. Never contacts GCP or providers.",
        allow_abbrev=False,
    )
    required = parser.add_argument_group("required")
    for flag, help_text in (
        ("--input", "local mirror root (the bucket's contents)"),
        ("--output", "summary file to create (never overwritten)"),
        ("--provider", "exact provider, e.g. openai"),
        ("--model", "exact model, e.g. gpt-6-luna"),
        ("--profile", "exact request profile, e.g. openai.gpt-6-luna.v1"),
        ("--workload", "exact workload, e.g. interactive-chat-v1"),
        ("--origin", "exact origin CLOUD/REGION, e.g. gcp/us-central1"),
    ):
        required.add_argument(flag, required=True, help=help_text)
    required.add_argument(
        "--start", required=True, type=_utc_argument, help="inclusive UTC"
    )
    required.add_argument(
        "--end", required=True, type=_utc_argument, help="exclusive UTC"
    )
    parser.add_argument(
        "--prefix", default="attempts", help="record prefix (default attempts)"
    )
    parser.add_argument(
        "--collector-policy-start",
        type=_utc_argument,
        help="report slot completeness from collector claims in the mirror",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    options = _parser().parse_args(argv)
    try:
        cloud, separator, region = options.origin.partition("/")
        if not separator or "/" in region:
            raise AnalyticsInputError("--origin must be CLOUD/REGION.")
        population = Population(
            provider=options.provider,
            model=options.model,
            request_profile_id=options.profile,
            workload_id=options.workload,
            origin_cloud=cloud,
            origin_region=region,
            start=options.start,
            end=options.end,
        )
    except AnalyticsInputError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    try:
        data = build(
            pathlib.Path(options.input),
            options.prefix,
            population,
            options.collector_policy_start,
        )
        created = write_summary(
            pathlib.Path(options.output),
            data,
            input_root=pathlib.Path(options.input),
        )
    except (AnalyticsInputError, AnalyticsOutputError) as error:
        print(f"Error: {error} Nothing written.", file=sys.stderr)
        return 1
    summary = json.loads(data)
    print(
        f"{'Wrote' if created else 'Unchanged (identical file exists)'}"
        f" {options.output}: {summary['evidence']['record_count']} records,"
        f" sha256 {hashlib.sha256(data).hexdigest()}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
