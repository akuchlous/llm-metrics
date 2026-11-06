"""Immutable, append-only benchmark records: one JSON object per attempt.

Owns the versioned single-document format for one benchmark attempt (request
facts plus its metric observations), its canonical encoding and validation,
the object name it is stored under, a create-only writer with bounded storage
retries and reconciliation, a read/validate path, and the mapping to and from
the `storage` table rows. It does not run providers, price requests, or decide
when to write: `real_benchmark` does that in its explicitly selected GCS
mode (`LLM_METRICS_RESULTS_BACKEND=gcs`); `benchmark.run_attempt()` and the
default SQL mode persist through `storage` (SQLAlchemy) only.

Record format (schema `llm-metrics.attempt.v1`), canonical JSON (UTF-8, keys
sorted, no insignificant whitespace, no NaN/Infinity)::

    {
      "attempt_id": "<32 lowercase hex: llm-metrics' own random UUID>",
      "environment": "prod" | "test",
      "observations": [{"metric": "<latency.METRICS key>", "value": <float>}],
      "recorded_at": "YYYY-MM-DDTHH:MM:SS.ffffffZ",   # UTC, fixed width
      "request": {<every REQUEST_FIELDS key; unknown facts are null>},
      "schema_version": "llm-metrics.attempt.v1"
    }

`request` holds exactly the `storage` requests-table facts other than the
row identity (`id`, `recorded_at`, `environment`, which are top-level here).
Observations are in `latency.METRICS` order and carry only metric and value;
provider, model, time, environment and attempt id are the parent's, exactly
as `storage.save_request` writes them. Nothing else can enter a record: the
builder copies named fields only, so prompts, responses, provider
diagnostics, headers, keys and credentials are excluded by construction.

Object name: `<prefix>/v1/requests/<environment>/<UTC date of recorded_at>/
<attempt_id>.json`. It is a pure function of the record, so a reader can
check that an object holds the record its name claims. The provider request
id is never part of the name (it is the provider's identity, may be missing,
and is not ours to keep unique).

Duplicate semantics: an object is created only if no object of that name
exists (server-side precondition, GCS `ifGenerationMatch=0`); the first
successful create wins and is never overwritten. Writing the identical bytes
again is idempotent and succeeds; different bytes under an existing name are
a conflict and fail. A record is durable only after the store confirms the
create, or confirms that the exact same bytes already exist.
"""

import base64
from collections.abc import Callable, Mapping
import dataclasses
import datetime
import hashlib
import json
import math
import re
import time
from typing import Protocol

from llm_metrics import latency
from llm_metrics import outcomes
from llm_metrics import providers

SCHEMA_VERSION = "llm-metrics.attempt.v1"
# Path segment that versions the object layout; bumped with the schema.
_LAYOUT_VERSION = "v1"

ENVIRONMENTS = ("test", "prod")

# Request facts of schema v1: the `storage` requests-table columns other than
# the row identity. Frozen with the schema version: adding a storage column
# does not change v1 records (tests pin this against `storage`).
REQUEST_FIELDS = (
    "provider",
    "model",
    "outcome",
    "input_tokens",
    "requested_max_output_tokens",
    "output_tokens",
    "input_price_per_1m",
    "output_price_per_1m",
    "input_cost",
    "output_cost",
    "total_cost",
    "failed_after_ms",
    "provider_request_id",
    "workload_id",
    "origin_cloud",
    "origin_region",
    "cache_policy",
    "cached_input_tokens",
    "request_profile_id",
    "cached_input_price_per_1m",
)
_REQUIRED_STRINGS = (
    "provider",
    "model",
    "workload_id",
    "origin_cloud",
    "origin_region",
    "request_profile_id",
)
_COUNT_FIELDS = (
    "input_tokens",
    "requested_max_output_tokens",
    "output_tokens",
    "cached_input_tokens",
)
_AMOUNT_FIELDS = (
    "input_price_per_1m",
    "output_price_per_1m",
    "input_cost",
    "output_cost",
    "total_cost",
    "failed_after_ms",
    "cached_input_price_per_1m",
)
# Known on success and unknown (null, never 0) on failure; the reverse holds
# for failed_after_ms. Mirrors the storage CHECK
# ck_requests_outcome_consistency.
_SUCCESS_ONLY_FIELDS = (
    "input_tokens",
    "output_tokens",
    "input_cost",
    "output_cost",
    "total_cost",
)
_NON_NULL_FIELDS = (
    "outcome",
    "requested_max_output_tokens",
    "input_price_per_1m",
    "output_price_per_1m",
    "cache_policy",
)
# measure_request always records both on success; their absence means a
# damaged or hand-made record.
_REQUIRED_SUCCESS_METRICS = ("total_latency", "ttft")

_ATTEMPT_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_RECORDED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")
_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
# GCS bucket naming rules (no dotted/domain buckets, which need verification),
# minus names Google reserves.
_BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,61}[a-z0-9]$")
_PREFIX_SEGMENT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
# Prefixes holding pilot backups or other non-record data; records must never
# be written among them, even though create-only writes could not overwrite.
_RESERVED_PREFIX_ROOTS = ("snapshots",)

RESULTS_BUCKET_VARIABLE = "LLM_METRICS_RESULTS_BUCKET"
RESULTS_PREFIX_VARIABLE = "LLM_METRICS_RESULTS_PREFIX"

DEFAULT_MAX_ATTEMPTS = 3
_BACKOFF_S = (0.5, 2.0)


class ResultStoreError(Exception):
    """Base error. Messages name object paths only, never record content."""


class InvalidRecordError(ResultStoreError, ValueError):
    """A record (or its bytes) violates schema v1. Nothing was written."""


class TargetConfigError(ResultStoreError, ValueError):
    """The bucket/prefix target is missing or unsafe. Nothing was written."""


class RecordConflictError(ResultStoreError):
    """A different object already exists under the record's name.

    The existing object is left untouched; the new record is NOT durable.
    """


class RecordIntegrityError(ResultStoreError):
    """Stored bytes differ from the bytes that were confirmed as written."""


class StoreUnavailableError(ResultStoreError):
    """Storage retries are exhausted; the record is NOT known to be durable."""


class ObjectExistsError(ResultStoreError):
    """Raised by an `ObjectStore` when the create-only precondition fails."""


class PermissionDeniedError(ResultStoreError):
    """The store refused the operation for lack of permission (HTTP 403)."""


class TransientStoreError(ResultStoreError):
    """Raised by an `ObjectStore` for a retryable failure (5xx, 429, network).

    The object may or may not have been created (an acknowledgement can be
    lost after the server committed it); callers reconcile by name.
    """


class ObjectStore(Protocol):
    """The two object operations records need. Implementations must be atomic.

    `create` writes the whole object or nothing, only if no object of that
    name exists, raising `ObjectExistsError` when one does and
    `TransientStoreError` for retryable failures. `read` returns the object's
    bytes, or None when it does not exist.
    """

    def create(self, bucket: str, name: str, data: bytes) -> None:
        ...

    def read(self, bucket: str, name: str) -> bytes | None:
        ...


@dataclasses.dataclass(frozen=True)
class ResultTarget:
    """A validated private bucket and fixed prefix records are written under."""

    bucket: str
    prefix: str

    def __post_init__(self):
        if not isinstance(self.bucket, str) or not _BUCKET_RE.match(
            self.bucket
        ):
            raise TargetConfigError(
                "Results bucket name is missing or invalid."
            )
        if self.bucket.startswith("goog") or "google" in self.bucket:
            raise TargetConfigError("Results bucket name is reserved.")
        if not isinstance(self.prefix, str) or not self.prefix:
            raise TargetConfigError("Results prefix must be set explicitly.")
        segments = self.prefix.split("/")
        if not all(_PREFIX_SEGMENT_RE.match(s) for s in segments):
            raise TargetConfigError(
                "Results prefix must be lowercase path segments without"
                " leading, trailing or repeated '/', '.' or '..'."
            )
        if segments[0] in _RESERVED_PREFIX_ROOTS:
            raise TargetConfigError("Results prefix is reserved.")


@dataclasses.dataclass(frozen=True)
class WriteResult:
    """A durable record: created now, or the identical bytes already existed."""

    name: str
    sha256: str
    created: bool


def target_from_environ(environ: Mapping[str, str]) -> ResultTarget:
    """Returns the explicitly configured target; there are no defaults.

    Raises:
        TargetConfigError: If either variable is missing, empty or unsafe.
    """
    return ResultTarget(
        environ.get(RESULTS_BUCKET_VARIABLE, ""),
        environ.get(RESULTS_PREFIX_VARIABLE, ""),
    )


def build_record(
    request: Mapping,
    results: list[Mapping],
    environment: str,
    *,
    attempt_id: str,
    recorded_at: str,
) -> dict:
    """Builds a validated v1 record from `benchmark.run_attempt`-shaped facts.

    Args:
        request: Request facts with every `REQUEST_FIELDS` key, except that
            "provider_request_id", "cached_input_tokens" and
            "cached_input_price_per_1m" may be omitted (null), as for
            `storage.save_request`. Other keys, e.g. a failure's
            "diagnostics", are ignored and never stored.
        results: Metric observations as produced by `latency`; only "metric"
            and "value" are kept, and their provider/model must match the
            request's.
        environment: "test" or "prod".
        attempt_id: llm-metrics' own id for the attempt (`uuid.uuid4().hex`).
        recorded_at: `storage.format_timestamp` text (UTC).

    Raises:
        InvalidRecordError: If any fact violates schema v1.
    """
    facts = {
        "provider_request_id": None,
        "cached_input_tokens": None,
        "cached_input_price_per_1m": None,
        **{key: request[key] for key in REQUEST_FIELDS if key in request},
    }
    missing = [key for key in REQUEST_FIELDS if key not in facts]
    if missing:
        raise InvalidRecordError(
            f"Request facts missing: {', '.join(missing)}."
        )
    for key in _AMOUNT_FIELDS:
        # One JSON number form per field: 1 and 1.0 must encode identically.
        if isinstance(facts[key], int) and not isinstance(facts[key], bool):
            facts[key] = float(facts[key])
    observations = []
    for result in results:
        if (result.get("provider"), result.get("model")) != (
            facts["provider"],
            facts["model"],
        ):
            raise InvalidRecordError(
                "Observation provider/model differs from the request's."
            )
        value = result.get("value")
        if isinstance(value, int) and not isinstance(value, bool):
            value = float(value)
        observations.append({"metric": result.get("metric"), "value": value})
    order = list(latency.METRICS)
    observations.sort(
        key=lambda o: order.index(o["metric"])
        if o["metric"] in order
        else len(order)
    )
    record = {
        "schema_version": SCHEMA_VERSION,
        "attempt_id": attempt_id,
        "recorded_at": recorded_at,
        "environment": environment,
        "request": facts,
        "observations": observations,
    }
    validate_record(record)
    return record


def _is_number(value) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def validate_record(record) -> None:
    """Checks a record against schema v1, including outcome consistency.

    Raises:
        InvalidRecordError: Describing the first violation (field names only).
    """
    if not isinstance(record, dict):
        raise InvalidRecordError("Record must be a JSON object.")
    expected = {
        "schema_version",
        "attempt_id",
        "recorded_at",
        "environment",
        "request",
        "observations",
    }
    if set(record) != expected:
        raise InvalidRecordError("Record has missing or unexpected keys.")
    if record["schema_version"] != SCHEMA_VERSION:
        raise InvalidRecordError("Unsupported record schema_version.")
    if not isinstance(record["attempt_id"], str) or not _ATTEMPT_ID_RE.match(
        record["attempt_id"]
    ):
        raise InvalidRecordError("attempt_id must be 32 lowercase hex digits.")
    recorded_at = record["recorded_at"]
    if not isinstance(recorded_at, str) or not _RECORDED_AT_RE.match(
        recorded_at
    ):
        raise InvalidRecordError("recorded_at must be fixed-width UTC text.")
    try:
        datetime.datetime.strptime(recorded_at, _TIMESTAMP_FORMAT)
    except ValueError:
        raise InvalidRecordError("recorded_at is not a valid time.") from None
    if record["environment"] not in ENVIRONMENTS:
        raise InvalidRecordError("environment must be 'test' or 'prod'.")
    _validate_request(record["request"])
    _validate_observations(record["request"], record["observations"])


def _validate_request(facts) -> None:
    if not isinstance(facts, dict) or set(facts) != set(REQUEST_FIELDS):
        raise InvalidRecordError("request has missing or unexpected facts.")
    for key in _NON_NULL_FIELDS:
        if facts[key] is None:
            raise InvalidRecordError(f"request.{key} must not be null.")
    for key in _REQUIRED_STRINGS:
        if not isinstance(facts[key], str) or not facts[key]:
            raise InvalidRecordError(
                f"request.{key} must be a non-empty string."
            )
    pid = facts["provider_request_id"]
    if pid is not None and (not isinstance(pid, str) or not pid):
        raise InvalidRecordError("request.provider_request_id must be text.")
    if facts["outcome"] not in outcomes.OUTCOMES:
        raise InvalidRecordError("request.outcome is not a known outcome.")
    # New attempts always carry their profile's declared policy; "unknown"
    # exists only for legacy SQL rows.
    if (
        facts["cache_policy"] not in providers.CACHE_POLICIES
        or facts["cache_policy"] == "unknown"
    ):
        raise InvalidRecordError("request.cache_policy is not a known policy.")
    for key in _COUNT_FIELDS:
        value = facts[key]
        if value is not None and (
            not isinstance(value, int) or isinstance(value, bool) or value < 0
        ):
            raise InvalidRecordError(
                f"request.{key} must be a non-negative integer."
            )
    if facts["requested_max_output_tokens"] < 1:
        raise InvalidRecordError(
            "request.requested_max_output_tokens must be >= 1."
        )
    for key in _AMOUNT_FIELDS:
        value = facts[key]
        if value is not None and (
            not isinstance(value, float) or not _is_number(value) or value < 0
        ):
            raise InvalidRecordError(
                f"request.{key} must be a finite non-negative number."
            )
    success = facts["outcome"] == outcomes.SUCCESS
    for key in _SUCCESS_ONLY_FIELDS:
        if (facts[key] is None) == success:
            raise InvalidRecordError(
                f"request.{key} must be {'known' if success else 'null'}"
                f" for outcome {facts['outcome']}."
            )
    if (facts["failed_after_ms"] is None) != success:
        raise InvalidRecordError(
            "request.failed_after_ms must be set exactly when the attempt"
            " failed."
        )
    if not success and facts["cached_input_tokens"] is not None:
        raise InvalidRecordError(
            "request.cached_input_tokens must be null for a failed attempt."
        )
    if (
        success
        and facts["cached_input_tokens"] is not None
        and facts["cached_input_tokens"] > facts["input_tokens"]
    ):
        raise InvalidRecordError(
            "request.cached_input_tokens exceeds input_tokens."
        )
    if (
        success
        and facts["output_tokens"] > facts["requested_max_output_tokens"]
    ):
        raise InvalidRecordError(
            "request.output_tokens exceeds the output cap."
        )


def _validate_observations(facts, observations) -> None:
    if not isinstance(observations, list):
        raise InvalidRecordError("observations must be a list.")
    metrics = []
    for observation in observations:
        if not isinstance(observation, dict) or set(observation) != {
            "metric",
            "value",
        }:
            raise InvalidRecordError("observation must have metric and value.")
        if observation["metric"] not in latency.METRICS:
            raise InvalidRecordError(
                "observation metric is not a known metric."
            )
        value = observation["value"]
        if not isinstance(value, float) or not _is_number(value) or value < 0:
            raise InvalidRecordError(
                "observation value must be a finite non-negative number."
            )
        metrics.append(observation["metric"])
    if len(set(metrics)) != len(metrics):
        raise InvalidRecordError("observation metrics must be unique.")
    order = list(latency.METRICS)
    if metrics != sorted(metrics, key=order.index):
        raise InvalidRecordError(
            "observations must be in latency.METRICS order."
        )
    if facts["outcome"] != outcomes.SUCCESS:
        if observations:
            raise InvalidRecordError(
                "A failed attempt must not have metric observations."
            )
    elif not set(_REQUIRED_SUCCESS_METRICS) <= set(metrics):
        raise InvalidRecordError(
            "A successful attempt must have total_latency and ttft."
        )


def encode_record(record: dict) -> bytes:
    """Returns the canonical bytes of a valid record (stable across runs).

    Raises:
        InvalidRecordError: If the record is invalid.
    """
    validate_record(record)
    return json.dumps(
        record,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _reject_duplicate_keys(pairs):
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise InvalidRecordError("Record JSON has duplicate keys.")
    return dict(pairs)


def _reject_constant(unused_name):
    raise InvalidRecordError("Record JSON has a non-finite number.")


def decode_record(data: bytes, *, expected_name: str | None = None) -> dict:
    """Parses, validates and canonicality-checks stored record bytes.

    Args:
        data: Object bytes.
        expected_name: If given, the name the object was read from; it must
            be the name this record would be written under (prefix aside).

    Raises:
        InvalidRecordError: If the bytes are not a canonical, valid v1 record
            or do not belong under `expected_name`.
    """
    try:
        record = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise InvalidRecordError("Record bytes are not UTF-8 JSON.") from None
    if encode_record(record) != data:
        raise InvalidRecordError("Record bytes are not in canonical form.")
    if expected_name is not None and not expected_name.endswith(
        "/" + _relative_name(record)
    ):
        raise InvalidRecordError(
            "Record does not belong under its object name."
        )
    return record


def _relative_name(record: dict) -> str:
    return (
        f"{_LAYOUT_VERSION}/requests/{record['environment']}/"
        f"{record['recorded_at'][:10]}/{record['attempt_id']}.json"
    )


def object_name(target: ResultTarget, record: dict) -> str:
    """Returns the object name of a valid record under `target`."""
    validate_record(record)
    return f"{target.prefix}/{_relative_name(record)}"


def write_record(
    store: ObjectStore,
    target: ResultTarget,
    record: dict,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
) -> WriteResult:
    """Durably writes one record exactly once, or fails without overwriting.

    Each storage attempt is a create-only upload of the canonical bytes. On a
    transient failure the outcome is ambiguous (the server may have committed
    the object before the acknowledgement was lost), so the next attempt's
    create-only precondition decides: if an object now exists, it is read and
    accepted only if byte-identical. After a confirmed create the object is
    read back and compared. Storage retries are bounded and never repeat a
    provider request: by the time a record exists, the measurement is over.

    Returns:
        WriteResult with `created` False when the identical object was already
        present (an idempotent replay or a late-acknowledged earlier attempt).

    Raises:
        InvalidRecordError: Nothing was attempted.
        RecordConflictError: A different object holds the name; not written.
        RecordIntegrityError: Read-back bytes differ from what was written.
        StoreUnavailableError: Retries exhausted; durability unknown/false.
        ResultStoreError: A permanent store failure (e.g. permission denied).
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1.")
    data = encode_record(record)
    name = object_name(target, record)
    digest = hashlib.sha256(data).hexdigest()
    for attempt in range(max_attempts):
        try:
            try:
                store.create(target.bucket, name, data)
                created = True
            except ObjectExistsError:
                created = False
            existing = store.read(target.bucket, name)
        except TransientStoreError:
            if attempt + 1 == max_attempts:
                break
            sleep(_BACKOFF_S[min(attempt, len(_BACKOFF_S) - 1)])
            continue
        if existing is None:
            # Confirmed (or pre-existing) yet absent: deleted underneath us or
            # an inconsistent store. Never treat it as durable.
            raise RecordIntegrityError(f"Object vanished after write: {name}")
        if existing != data:
            if created:
                raise RecordIntegrityError(f"Read-back mismatch: {name}")
            raise RecordConflictError(f"A different record exists: {name}")
        return WriteResult(name=name, sha256=digest, created=created)
    raise StoreUnavailableError(
        f"Storage unavailable after {max_attempts} attempts; record not"
        f" confirmed durable: {name}"
    )


PREFLIGHT_KIND = "llm-metrics.preflight.v1"


def preflight(
    store: ObjectStore, target: ResultTarget, *, probe_id: str, now: str
) -> str:
    """Proves create, read and no-overwrite on `target` with a real probe.

    Creates a small probe object under `<prefix>/v1/preflight/<date>/`
    (outside the `requests/` record namespace), reads it back, then tries to
    create the same name with different bytes, which must be refused, and
    confirms the original bytes survived. Run before a paid request: if any
    step fails, nothing should be requested. A passed preflight does not
    guarantee a later write succeeds.

    Args:
        probe_id: A fresh `uuid.uuid4().hex`.
        now: `storage.format_timestamp` text, used for the date and content.

    Returns:
        The probe object's name.

    Raises:
        InvalidRecordError: If probe_id or now is malformed.
        RecordIntegrityError: If read-back differs or an overwrite succeeded.
        ResultStoreError: Any store failure (including transient ones; the
            preflight does not retry).
    """
    if not _ATTEMPT_ID_RE.match(probe_id) or not _RECORDED_AT_RE.match(now):
        raise InvalidRecordError("Preflight probe id or time is malformed.")
    name = (
        f"{target.prefix}/{_LAYOUT_VERSION}/preflight/{now[:10]}/"
        f"{probe_id}.json"
    )
    data = json.dumps(
        {"kind": PREFLIGHT_KIND, "probe_id": probe_id, "created_at": now},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    store.create(target.bucket, name, data)
    if store.read(target.bucket, name) != data:
        raise RecordIntegrityError(f"Preflight read-back mismatch: {name}")
    try:
        store.create(target.bucket, name, data + b" ")
    except ObjectExistsError:
        pass
    else:
        raise RecordIntegrityError(
            f"Store allowed an overwrite; create-only is not enforced: {name}"
        )
    if store.read(target.bucket, name) != data:
        raise RecordIntegrityError(f"Preflight object changed: {name}")
    return name


def read_record(store: ObjectStore, target: ResultTarget, name: str) -> dict:
    """Reads and validates one record by object name.

    Raises:
        InvalidRecordError: If the name is outside `target` or the bytes are
            not a valid record for that name.
        ResultStoreError: If the object does not exist.
    """
    if not name.startswith(target.prefix + "/"):
        raise InvalidRecordError("Object name is outside the results prefix.")
    data = store.read(target.bucket, name)
    if data is None:
        raise ResultStoreError(f"No such record: {name}")
    return decode_record(data, expected_name=name)


def to_storage_rows(record: dict) -> tuple[dict, list[dict]]:
    """Maps a record to `storage` row values (requests row, observation rows).

    The request row has every requests-table column; observation rows have
    every observations column except the database-assigned integer `id`.
    """
    validate_record(record)
    facts = record["request"]
    request_row = {
        "id": record["attempt_id"],
        "recorded_at": record["recorded_at"],
        "environment": record["environment"],
        **facts,
    }
    observation_rows = [
        {
            "recorded_at": record["recorded_at"],
            "environment": record["environment"],
            "provider": facts["provider"],
            "model": facts["model"],
            "metric": o["metric"],
            "value": o["value"],
            "request_id": record["attempt_id"],
        }
        for o in record["observations"]
    ]
    return request_row, observation_rows


def from_storage_rows(
    request_row: Mapping, observation_rows: list[Mapping]
) -> dict:
    """Builds a record from one stored attempt (the inverse of to_storage_rows).

    For importing an existing attempt (e.g. a verified pilot export) without
    changing its identity or time. Observations must belong to the attempt.

    Raises:
        InvalidRecordError: If rows are inconsistent or violate schema v1.
    """
    for row in observation_rows:
        if (
            row.get("request_id"),
            row.get("recorded_at"),
            row.get("environment"),
        ) != (
            request_row.get("id"),
            request_row.get("recorded_at"),
            request_row.get("environment"),
        ):
            raise InvalidRecordError(
                "Observation row does not belong to the request row."
            )
    return build_record(
        request_row,
        list(observation_rows),
        request_row.get("environment"),
        attempt_id=request_row.get("id"),
        recorded_at=request_row.get("recorded_at"),
    )


class GcsObjectStore:
    """`ObjectStore` over Google Cloud Storage (google-cloud-storage client).

    `create` is a single-request upload with `if_generation_match=0` (create
    only if absent) and the content MD5, so the server rejects both overwrite
    and corrupted bytes. The client library's own retries are disabled
    (`retry=None`) so `write_record` alone bounds and reconciles retries.
    Exceptions are translated into this module's types with sanitized
    messages (exception class and HTTP code only, never response bodies).
    """

    def __init__(self, client=None):
        """Wraps a `google.cloud.storage.Client`.

        Args:
            client: An existing client (tests inject a fake). If None, a
                client is created from Application Default Credentials; this
                is the only place that touches credentials, and only when a
                store is constructed, never at import.
        """
        if client is None:
            # Imported lazily so importing this module loads no cloud
            # client or credentials.
            # pylint: disable-next=import-outside-toplevel
            from google.cloud import storage as gcs

            client = gcs.Client()
        self._client = client

    def create(self, bucket: str, name: str, data: bytes) -> None:
        blob = self._client.bucket(bucket).blob(name)
        blob.md5_hash = base64.b64encode(hashlib.md5(data).digest()).decode()
        try:
            blob.upload_from_string(
                data,
                content_type="application/json",
                if_generation_match=0,
                retry=None,
            )
        except Exception as error:  # pylint: disable=broad-exception-caught
            translated = _translate(error)
        else:
            return
        if isinstance(translated, PermissionDeniedError):
            # A caller allowed to create but not to replace objects may get
            # 403 instead of 412 for an existing name. Report "exists" only
            # when the object is really there, so a missing grant still fails.
            if self.read(bucket, name) is not None:
                raise ObjectExistsError("Object already exists (HTTP 403).")
        raise translated

    def read(self, bucket: str, name: str) -> bytes | None:
        blob = self._client.bucket(bucket).blob(name)
        try:
            return blob.download_as_bytes(retry=None)
        except Exception as error:  # pylint: disable=broad-exception-caught
            translated = _translate(error)
            if isinstance(translated, _NotFound):
                return None
            raise translated from None

    def created_time(self, bucket: str, name: str) -> datetime.datetime | None:
        """Server-recorded creation time of an object, or None if absent."""
        try:
            blob = self._client.bucket(bucket).get_blob(name, retry=None)
        except Exception as error:  # pylint: disable=broad-exception-caught
            raise _translate(error) from None
        return None if blob is None else blob.time_created

    def list_names(self, bucket: str, prefix: str) -> list[str]:
        """Names of all objects under `prefix` (read-only listing)."""
        try:
            return [
                blob.name
                for blob in self._client.list_blobs(
                    bucket, prefix=prefix, retry=None
                )
            ]
        except Exception as error:  # pylint: disable=broad-exception-caught
            raise _translate(error) from None


class _NotFound(ResultStoreError):
    """Internal: the object does not exist (404)."""


# HTTP codes worth retrying for an idempotent create-only upload or a read.
_TRANSIENT_CODES = frozenset({408, 429, 500, 502, 503, 504})


def _translate(error: Exception) -> ResultStoreError:
    """Maps a client/transport exception to a sanitized module error."""
    code = getattr(error, "code", None)
    kind = type(error).__name__
    if code == 412:
        return ObjectExistsError("Object already exists (HTTP 412).")
    if code == 404:
        return _NotFound("Object not found (HTTP 404).")
    if code == 403:
        return PermissionDeniedError(f"Permission denied: {kind} (HTTP 403).")
    if isinstance(code, int):
        if code in _TRANSIENT_CODES:
            return TransientStoreError(
                f"Transient storage error {kind} (HTTP {code})."
            )
        return ResultStoreError(
            f"Storage request failed: {kind} (HTTP {code})."
        )
    # No HTTP status: connection reset, timeout, DNS. The request may or may
    # not have reached the server, which create-only reconciliation handles.
    if isinstance(error, (ConnectionError, TimeoutError)) or kind in (
        "ConnectionError",
        "Timeout",
        "ReadTimeout",
        "ConnectTimeout",
        "ChunkedEncodingError",
        "TransportError",
    ):
        return TransientStoreError(f"Transient storage error {kind}.")
    return ResultStoreError(f"Storage request failed: {kind}.")
