"""Scheduled 15-minute OpenAI collector with atomic slot claims (bounded pilot).

Usage (run by Cloud Scheduler -> Cloud Run Job; takes no arguments):
    python -m llm_metrics.scheduled_collector

A separately selected execution path: the one-off commands (`real_benchmark`
in SQL or GCS mode, `real_smoke`, `gcs_smoke`) are unchanged. Each invocation
makes AT MOST ONE paid OpenAI request, and only when all of these hold:

1. Fixed scope: target `openai.gpt-6-luna.v1`, workload `interactive-chat-v1`,
   GCS results backend, origin cloud "gcp". None of these can be chosen by the
   caller; there are no arguments.
2. Activation policy from the job's environment (`LLM_METRICS_COLLECTOR_START`
   / `_EXPIRES`, UTC "YYYY-MM-DDTHH:MM:SSZ"): the start lies on a quarter-hour
   boundary and the expiry is exactly 24 hours later, so the policy allows
   exactly `MAX_SLOTS` (96) slots. A policy that is missing, malformed, longer,
   shorter or unaligned is refused. Changing it needs permission to update the
   job; a scheduler identity with only `run.invoker` cannot override it.
3. The current UTC quarter-hour slot (:00/:15/:30/:45, from this process's
   clock, never from an argument) is inside the policy and the invocation
   starts at most `LATE_LIMIT` (7 minutes) after the slot began.
4. A storage preflight (`object_results.preflight`) passes.
5. An immutable claim object for exactly this slot, profile, workload and
   origin is created with a create-only precondition and read back unchanged.
   A claim that already exists means another invocation owns the slot: skip
   without any provider call. A claim that fails or is ambiguous is a refusal.
   The claim names the attempt id the GCS record will use.
6. The server's creation time of the claim agrees with this process's clock
   within `MAX_CLOCK_SKEW`, and the policy expiry and late limit still hold
   immediately before the request.

A claimed slot stays consumed whatever happens afterwards (crash, provider
failure, failed write): nothing here ever repeats a provider request. The
claim does NOT close the window between a paid response and the durable
record; a process killed in that window leaves a claim without a record,
which `collector_audit` reports.

Limits: wall-clock scheduling relies on the container clock (checked against
GCS server time) and on Cloud Scheduler delivery; a missed delivery is a
missed slot, never made up later. The gate constrains this code path only:
it cannot stop someone with project permissions from running other code with
the same credentials, and it caps requests, not total GCP or OpenAI charges.

Mode `LLM_METRICS_COLLECTOR_MODE`:
- "prod": real requests, claims under `<prefix>/v1/claims/prod/`, records
  with environment "prod".
- "dryrun": no provider and no key (refused if any provider key is set);
  claims under `<prefix>/v1/claims/dryrun/`, the simulated provider, records
  with environment "test", plus a duplicate-claim check.

Output: one JSON log line per event (Cloud Logging reads `severity`), with
sanitized metadata only: never the key, prompt, response, record payload or
raw provider errors.

Exit codes: 0 recorded (success or recorded provider failure), duplicate
skip, policy not active, or dry run passed; 2 configuration refused or the
provider rejected the request (nothing recorded); 3 a request was made but its
record is not confirmed durable; 4 refused after the slot check (late start,
claim failure, clock skew, expiry reached) with no request.
"""

import dataclasses
import datetime
import json
import os
import sys
import uuid

from llm_metrics import benchmark
from llm_metrics import config
from llm_metrics import http_streaming
from llm_metrics import object_results
from llm_metrics import pricing
from llm_metrics import providers
from llm_metrics import real_benchmark
from llm_metrics import storage
from llm_metrics import targets
from llm_metrics import workloads

COMPONENT = "llm-metrics-collector"
MODE_VARIABLE = "LLM_METRICS_COLLECTOR_MODE"
START_VARIABLE = "LLM_METRICS_COLLECTOR_START"
EXPIRES_VARIABLE = "LLM_METRICS_COLLECTOR_EXPIRES"
MODES = ("prod", "dryrun")

SLOT = datetime.timedelta(minutes=15)
MAX_SLOTS = 96
WINDOW = SLOT * MAX_SLOTS  # 24 hours
LATE_LIMIT = datetime.timedelta(minutes=7)
MAX_CLOCK_SKEW = datetime.timedelta(seconds=120)

TARGET = targets.OPENAI
WORKLOAD_ID = "interactive-chat-v1"
ORIGIN_CLOUD = "gcp"
CLAIM_KIND = "llm-metrics.claim.v1"

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_NOT_PERSISTED = real_benchmark.EXIT_NOT_PERSISTED  # 3
EXIT_REFUSED = 4

_POLICY_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_UTC = datetime.timezone.utc


class CollectorConfigError(ValueError):
    """The collector's configuration or policy is invalid (nothing done)."""


@dataclasses.dataclass(frozen=True)
class Policy:
    """A finite activation window of exactly MAX_SLOTS quarter-hour slots."""

    start: datetime.datetime
    expires: datetime.datetime

    def __post_init__(self):
        if self.start.tzinfo is None or self.expires.tzinfo is None:
            raise CollectorConfigError("Policy times must be UTC.")
        if self.start != slot_start(self.start):
            raise CollectorConfigError(
                "Policy start must be a UTC quarter-hour boundary."
            )
        if self.expires - self.start != WINDOW:
            raise CollectorConfigError(
                f"Policy must span exactly {MAX_SLOTS} slots (24 hours)."
            )

    def slots(self) -> list[datetime.datetime]:
        """Every allowed slot start, in order (exactly MAX_SLOTS)."""
        return [self.start + SLOT * i for i in range(MAX_SLOTS)]

    def allows(self, slot: datetime.datetime) -> bool:
        return self.start <= slot < self.expires

    def as_dict(self) -> dict:
        return {
            "start": format_utc(self.start),
            "expires": format_utc(self.expires),
            "max_slots": MAX_SLOTS,
        }


def format_utc(moment: datetime.datetime) -> str:
    return moment.astimezone(_UTC).strftime(_POLICY_FORMAT)


def parse_utc(text: str | None, variable: str) -> datetime.datetime:
    try:
        return datetime.datetime.strptime(text or "", _POLICY_FORMAT).replace(
            tzinfo=_UTC
        )
    except ValueError:
        raise CollectorConfigError(
            f"{variable} must be UTC 'YYYY-MM-DDTHH:MM:SSZ'."
        ) from None


def policy_from_environ(environ) -> Policy:
    """Returns the validated activation policy.

    Raises:
        CollectorConfigError: Missing, malformed or not exactly 96 slots.
    """
    return Policy(
        parse_utc(environ.get(START_VARIABLE), START_VARIABLE),
        parse_utc(environ.get(EXPIRES_VARIABLE), EXPIRES_VARIABLE),
    )


def slot_start(moment: datetime.datetime) -> datetime.datetime:
    """The UTC quarter-hour slot containing `moment`."""
    moment = moment.astimezone(_UTC)
    return moment.replace(
        minute=moment.minute - moment.minute % 15, second=0, microsecond=0
    )


def claim_name(
    results_target: object_results.ResultTarget,
    mode: str,
    origin: tuple[str, str],
    slot: datetime.datetime,
) -> str:
    """Claim object name: one per (mode, profile, workload, origin, slot)."""
    return (
        f"{results_target.prefix}/v1/claims/{mode}/{TARGET.profile_id}/"
        f"{WORKLOAD_ID}/{origin[0]}-{origin[1]}/"
        f"{slot.strftime('%Y-%m-%d')}/{slot.strftime('%H%M')}.json"
    )


def claim_bytes(
    *,
    mode: str,
    origin: tuple[str, str],
    slot: datetime.datetime,
    attempt_id: str,
    claimed_at: datetime.datetime,
    policy: Policy,
) -> bytes:
    """Canonical claim content (no secrets; metadata only)."""
    return json.dumps(
        {
            "kind": CLAIM_KIND,
            "mode": mode,
            "slot": format_utc(slot),
            "attempt_id": attempt_id,
            "claimed_at": storage.format_timestamp(claimed_at),
            "profile_id": TARGET.profile_id,
            "workload_id": WORKLOAD_ID,
            "origin_cloud": origin[0],
            "origin_region": origin[1],
            "policy": policy.as_dict(),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


class _Log:
    """Structured, sanitized JSON event lines for Cloud Logging."""

    def __init__(self, mode: str | None):
        self.base = {"component": COMPONENT, "mode": mode}

    def event(self, event: str, severity: str = "INFO", **fields) -> None:
        line = {
            "severity": severity,
            **self.base,
            "event": event,
            **{k: v for k, v in fields.items() if v is not None},
        }
        line["message"] = f"{COMPONENT} {event}"
        print(json.dumps(line, sort_keys=True), flush=True)


def _validate_config(environ) -> tuple:
    """Returns (mode, origin, results_target, policy); no I/O."""
    mode = environ.get(MODE_VARIABLE, "")
    if mode not in MODES:
        raise CollectorConfigError(
            f"{MODE_VARIABLE} must be 'prod' or 'dryrun'."
        )
    try:
        origin = config.get_origin(environ)
        backend = config.get_results_backend(environ)
        results_target = object_results.target_from_environ(environ)
    except (config.ConfigError, object_results.TargetConfigError) as e:
        raise CollectorConfigError(str(e)) from None
    if backend != "gcs":
        raise CollectorConfigError(
            f"{config.RESULTS_BACKEND_VARIABLE} must be 'gcs'."
        )
    if origin[0] != ORIGIN_CLOUD:
        raise CollectorConfigError(
            f"{config.ORIGIN_CLOUD_VARIABLE} must be '{ORIGIN_CLOUD}'."
        )
    keys = [
        t.api_key_variable
        for t in targets.BENCHMARK_TARGETS
        if environ.get(t.api_key_variable)
    ]
    if mode == "dryrun" and keys:
        raise CollectorConfigError(
            "Dry run refuses to start with provider credentials present."
        )
    return mode, origin, results_target, policy_from_environ(environ)


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(_UTC)


def run(
    environ=None,
    *,
    now=_utcnow,
    store_factory=object_results.GcsObjectStore,
    adapters=None,
) -> int:
    """One scheduled invocation; see the module docstring for exit codes."""
    environ = os.environ if environ is None else environ
    adapters = real_benchmark.ADAPTERS if adapters is None else adapters
    started = now()
    slot = slot_start(started)
    log = _Log(environ.get(MODE_VARIABLE) or None)
    timing = {
        "slot": format_utc(slot),
        "started_at": storage.format_timestamp(started),
    }

    try:
        mode, origin, results_target, policy = _validate_config(environ)
    except CollectorConfigError as e:
        log.event("config_refused", "ERROR", reason=str(e), **timing)
        return EXIT_CONFIG
    timing["policy_start"] = format_utc(policy.start)
    timing["policy_expires"] = format_utc(policy.expires)

    # Outside the window is a quiet no-op: an enabled scheduler after expiry
    # (or before activation) never reaches the provider.
    if not policy.allows(slot):
        state = (
            "policy_expired" if slot >= policy.expires else "policy_not_started"
        )
        log.event(state, "INFO", **timing)
        return EXIT_OK
    if started - slot > LATE_LIMIT:
        log.event("late_start", "ERROR", **timing)
        return EXIT_REFUSED

    api_key = None
    if mode == "prod":
        api_key = environ.get(TARGET.api_key_variable, "")
        if not api_key:
            log.event(
                "config_refused", "ERROR",
                reason=f"{TARGET.api_key_variable} is not set.", **timing,
            )  # fmt: skip
            return EXIT_CONFIG
    try:
        workload = workloads.get_workload(WORKLOAD_ID)
        price = pricing.price_for(TARGET.provider, TARGET.model)
    except (KeyError, ValueError) as e:
        log.event("config_refused", "ERROR", reason=type(e).__name__, **timing)
        return EXIT_CONFIG

    attempt_id = uuid.uuid4().hex
    name = claim_name(results_target, mode, origin, slot)
    timing.update(attempt_id=attempt_id, claim=name)
    try:
        store = store_factory()
        object_results.preflight(
            store,
            results_target,
            probe_id=uuid.uuid4().hex,
            now=storage.format_timestamp(now()),
        )
        claimed_at = now()
        data = claim_bytes(
            mode=mode, origin=origin, slot=slot, attempt_id=attempt_id,
            claimed_at=claimed_at, policy=policy,
        )  # fmt: skip
        try:
            store.create(results_target.bucket, name, data)
        except object_results.ObjectExistsError:
            log.event("duplicate_skip", "WARNING", **timing)
            return EXIT_OK
        if store.read(results_target.bucket, name) != data:
            raise object_results.RecordIntegrityError(
                "Claim read-back differs."
            )
        server_time = store.created_time(results_target.bucket, name)
    except Exception as e:  # pylint: disable=broad-except
        # Includes ambiguous creates: the slot may now be claimed, but this
        # invocation cannot prove it owns it, so it must not spend.
        log.event("claim_failed", "ERROR", error=type(e).__name__, **timing)
        return EXIT_REFUSED
    if server_time is None or abs(server_time - claimed_at) > MAX_CLOCK_SKEW:
        log.event("clock_skew", "ERROR", **timing)
        return EXIT_REFUSED
    log.event("slot_claimed", "INFO", **timing)

    if mode == "dryrun":
        return _dry_run(
            store, results_target, name, data, origin, log, timing, now
        )

    # Last gate immediately before the paid request.
    before_call = now()
    if before_call >= policy.expires or before_call - slot > LATE_LIMIT:
        log.event("expired_before_call", "ERROR", **timing)
        return EXIT_REFUSED
    provider = adapters[TARGET.provider](api_key)
    real_benchmark.announce(TARGET, workload, origin, price)
    log.event("attempt_initiated", "INFO", **timing)
    try:
        request, results = benchmark.measure_attempt(
            provider, workload, origin=origin
        )
    except http_streaming.RequestRejected as e:
        log.event(
            "provider_rejected", "ERROR", error=type(e).__name__, **timing
        )
        return EXIT_CONFIG
    except ValueError as e:
        log.event("config_refused", "ERROR", reason=str(e), **timing)
        return EXIT_CONFIG
    return _persist(
        store, results_target, request, results, "prod", log, timing, now
    )


def _persist(
    store, results_target, request, results, environment, log, timing, now
):
    """Writes the record once; never repeats the provider request."""
    try:
        record = object_results.build_record(
            request,
            results,
            environment,
            attempt_id=timing["attempt_id"],
            recorded_at=storage.format_timestamp(now()),
        )
        written = object_results.write_record(store, results_target, record)
    except object_results.ResultStoreError as e:
        log.event(
            "not_persisted", "ERROR", outcome=request["outcome"],
            error=type(e).__name__, **timing,
        )  # fmt: skip
        return EXIT_NOT_PERSISTED
    success = request["outcome"] == "success"
    log.event(
        "recorded_success" if success else "recorded_failure",
        "INFO" if success else "WARNING",
        outcome=request["outcome"],
        record=written.name,
        sha256=written.sha256,
        **timing,
    )
    return EXIT_OK


def _dry_run(
    store, results_target, name, data, origin, log, timing, now
) -> int:
    """No provider: prove duplicate refusal, write a synthetic test record."""
    try:
        try:
            store.create(results_target.bucket, name, data + b" ")
        except object_results.ObjectExistsError:
            pass
        else:
            raise object_results.RecordIntegrityError(
                "Duplicate claim allowed."
            )
        if store.read(results_target.bucket, name) != data:
            raise object_results.RecordIntegrityError("Claim changed.")
    except Exception as e:  # pylint: disable=broad-except
        log.event("claim_failed", "ERROR", error=type(e).__name__, **timing)
        return EXIT_REFUSED
    log.event("dryrun_duplicate_refused", "INFO", **timing)
    provider = providers.DummyProvider(
        first_token_delay_s=0.0, inter_token_delay_s=0.0
    )
    workload = workloads.get_workload(workloads.DEFAULT_WORKLOAD_ID)
    request, results = benchmark.measure_attempt(
        provider, workload, origin=origin
    )
    return _persist(
        store, results_target, request, results, "test", log, timing, now
    )


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args:
        # No arguments on purpose: nothing a caller passes can select a
        # slot, time, target or policy.
        print(
            "Usage: python -m llm_metrics.scheduled_collector", file=sys.stderr
        )
        return EXIT_CONFIG
    return run()


if __name__ == "__main__":
    sys.exit(main())
