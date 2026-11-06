"""Storage-only smoke test of the GCS results backend: no provider, no key.

Usage: python -m llm_metrics.gcs_smoke

Proves, with the identity the process runs as (on Cloud Run: the job's
service account), that the configured results target accepts exactly the
operations GCS-backed benchmarking needs, without any paid request:

1. the `object_results.preflight` probe (create, read back, refused
   overwrite) that `real_benchmark` runs before a paid request;
2. a synthetic attempt record written with `object_results.write_record`:
   measured from the in-process simulated provider (no network), stored with
   environment "test", so it lands under `<prefix>/v1/requests/test/` and
   never in the real `prod` namespace;
3. an identical replay is accepted without creating anything;
4. a conflicting record under the same name is refused;
5. the record reads back and validates.

Requires LLM_METRICS_RESULTS_BACKEND=gcs, LLM_METRICS_ORIGIN_CLOUD=gcp and the
explicit bucket/prefix. Refuses to run if any provider API key variable is
set, so it cannot be mistaken for, or turned into, a paid run. Prints object
names and hashes only, never record content.

Exit codes: 0 all checks passed; 1 a storage check failed; 2 refused
(configuration), nothing was written.
"""

import copy
import datetime
import os
import sys
import uuid

from llm_metrics import benchmark
from llm_metrics import config
from llm_metrics import object_results
from llm_metrics import providers
from llm_metrics import storage
from llm_metrics import targets
from llm_metrics import workloads

ENVIRONMENT = "test"


def _now() -> str:
    return storage.format_timestamp(
        datetime.datetime.now(datetime.timezone.utc)
    )


def _refusal(environ) -> tuple[object_results.ResultTarget | None, str | None]:
    """Returns (target, None) or (None, reason); no network access."""
    keys = sorted(
        t.api_key_variable
        for t in targets.BENCHMARK_TARGETS
        if environ.get(t.api_key_variable)
    )
    if keys:
        return None, (
            f"provider credentials are present ({', '.join(keys)}); the storage"
            " smoke must run without any provider key"
        )
    try:
        if config.get_results_backend(environ) != "gcs":
            return None, f"{config.RESULTS_BACKEND_VARIABLE} must be 'gcs'"
        if config.get_origin(environ)[0] != "gcp":
            return None, f"{config.ORIGIN_CLOUD_VARIABLE} must be 'gcp'"
        return object_results.target_from_environ(environ), None
    except (config.ConfigError, object_results.TargetConfigError) as e:
        return None, str(e)


def _synthetic_record(origin: tuple[str, str]) -> dict:
    """A valid v1 record from one simulated (no-network, unpriced) attempt."""
    provider = providers.DummyProvider(
        first_token_delay_s=0.0, inter_token_delay_s=0.0
    )
    workload = workloads.get_workload(workloads.DEFAULT_WORKLOAD_ID)
    request, results = benchmark.measure_attempt(
        provider, workload, origin=origin
    )
    return object_results.build_record(
        request,
        results,
        ENVIRONMENT,
        attempt_id=uuid.uuid4().hex,
        recorded_at=_now(),
    )


def run(environ=None, *, store_factory=object_results.GcsObjectStore) -> int:
    """Runs the smoke checks; see the module docstring for exit codes."""
    environ = os.environ if environ is None else environ
    target, reason = _refusal(environ)
    if reason:
        print(f"Error: {reason}. Nothing was written.", file=sys.stderr)
        return 2
    origin = config.get_origin(environ)
    print(f"GCS storage smoke: gs://{target.bucket}/{target.prefix}/")
    step = "client"
    try:
        store = store_factory()
        step = "preflight"
        probe = object_results.preflight(
            store, target, probe_id=uuid.uuid4().hex, now=_now()
        )
        print(f"  PASS preflight create/read/no-overwrite: {probe}")
        step = "write"
        record = _synthetic_record(origin)
        first = object_results.write_record(store, target, record)
        if not first.created:
            raise object_results.RecordIntegrityError(
                "Synthetic record already existed."
            )
        print(f"  PASS create synthetic record: {first.name}")
        print(f"       sha256 {first.sha256}")
        step = "replay"
        again = object_results.write_record(store, target, record)
        if again.created or again.sha256 != first.sha256:
            raise object_results.RecordIntegrityError("Replay was not a no-op.")
        print("  PASS identical replay accepted, nothing created")
        step = "conflict"
        conflicting = copy.deepcopy(record)
        conflicting["observations"][0]["value"] += 1.0
        try:
            object_results.write_record(store, target, conflicting)
        except object_results.RecordConflictError:
            print("  PASS conflicting record refused, original kept")
        else:
            raise object_results.RecordIntegrityError(
                "A conflicting record was accepted."
            )
        step = "read"
        if object_results.read_record(store, target, first.name) != record:
            raise object_results.RecordIntegrityError("Read-back differs.")
        print("  PASS read back and validated")
    except Exception as e:  # pylint: disable=broad-except
        # Class and module-sanitized message only (object names, codes).
        detail = (
            f": {e}" if isinstance(e, object_results.ResultStoreError) else ""
        )
        print(f"FAIL at {step} ({type(e).__name__}{detail}).", file=sys.stderr)
        return 1
    print("GCS storage smoke: all checks passed (no provider request).")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args:
        print("Usage: python -m llm_metrics.gcs_smoke", file=sys.stderr)
        return 2
    return run()


if __name__ == "__main__":
    sys.exit(main())
