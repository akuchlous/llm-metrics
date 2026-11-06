"""Makes exactly ONE real, paid benchmark request to one chosen provider.

Usage:
    python -m llm_metrics.real_benchmark --provider PROVIDER --real
        [--workload WORKLOAD_ID] [--debug]

PROVIDER is one of the benchmark targets (`targets.BENCHMARK_TARGETS`):
openai, anthropic, google, xai. The workload defaults to
`interactive-chat-v1`. `--real` is required: it confirms that a paid request
is intended, so a mistyped or copied command never spends money.

One provider x one workload x one attempt, run only when invoked explicitly:
there is no "all providers" option, no loop, and no retry, and having several
API keys set never causes more than the one chosen request. Only the chosen
provider's key is read (from its conventional environment variable, never
from a file or argument). Every refusal (bad arguments, unknown provider or
workload, missing key, invalid origin, unpriceable workload) happens before
any network access.

The attempt is stored with environment "prod" (real data), its workload id,
request profile id, origin, cache policy, provider-reported tokens and the
rates used for its cost. The command prints only safe metadata before the
request and a summary after it: never the API key, the prompt, the response,
or provider error messages. `--debug` prints sanitized failure diagnostics to
stderr; they are never stored.

Results backend (`LLM_METRICS_RESULTS_BACKEND`, see `config`):
- "sql" (default): SQL storage. A non-local origin requires an explicit
  PostgreSQL `LLM_METRICS_DATABASE_URL`, and the database is checked before
  the request.
- "gcs": one immutable `object_results` record in the explicitly configured
  private bucket/prefix (`LLM_METRICS_RESULTS_BUCKET`/`_PREFIX`). Allowed only
  for origin cloud "gcp" and the OpenAI target. Before the request, a real
  create/read/no-overwrite probe proves the target works. The attempt id is
  fixed before the request; the record is written once after it, and the
  provider request is never repeated.

Exit codes: 0 the attempt was recorded (successful or failed: a failure is a
valid benchmark result); 2 nothing was requested, or the provider rejected the
request itself (nothing recorded); 3 (GCS mode) a request was made but its
record is NOT confirmed durable.
"""

import datetime
import os
import sys
import uuid

from llm_metrics import anthropic_provider
from llm_metrics import benchmark
from llm_metrics import config
from llm_metrics import google_provider
from llm_metrics import http_streaming
from llm_metrics import object_results
from llm_metrics import openai_provider
from llm_metrics import pricing
from llm_metrics import storage
from llm_metrics import targets
from llm_metrics import workloads
from llm_metrics import xai_provider

USAGE = (
    "Usage: python -m llm_metrics.real_benchmark --provider PROVIDER --real"
    " [--workload WORKLOAD_ID] [--debug]"
)
ENVIRONMENT = "prod"
# A paid request was made, but its GCS record is not confirmed durable.
EXIT_NOT_PERSISTED = 3
# GCS mode is limited to this origin cloud and this request profile.
_GCS_ORIGIN_CLOUD = "gcp"
_GCS_PROFILE_ID = targets.OPENAI.profile_id
# Schemes accepted for LLM_METRICS_DATABASE_URL when ORIGIN_CLOUD is not "local".
# SQLite and bare paths resolve to ephemeral container storage and are not durable.
_CLOUD_APPROVED_DB_SCHEMES = frozenset({"postgresql", "postgresql+psycopg2"})
# The adapter class of each benchmark target, by provider name.
ADAPTERS = {
    "openai": openai_provider.OpenAIProvider,
    "anthropic": anthropic_provider.AnthropicProvider,
    "google": google_provider.GoogleProvider,
    "xai": xai_provider.XAIProvider,
}


def _parse_args(args: list[str]) -> tuple[str, str, bool]:
    """Returns (provider, workload_id, debug).

    Raises:
        ValueError: With `USAGE` for missing `--provider` or `--real`, repeated
            or unknown options, or options without values.
    """
    options: dict[str, str | None] = {}
    remaining = list(args)
    while remaining:
        option = remaining.pop(0)
        if option in options:
            raise ValueError(USAGE)
        if option in ("--provider", "--workload"):
            if not remaining:
                raise ValueError(USAGE)
            options[option] = remaining.pop(0)
        elif option in ("--real", "--debug"):
            options[option] = None
        else:
            raise ValueError(USAGE)
    if "--provider" not in options or "--real" not in options:
        raise ValueError(USAGE)
    return (
        options["--provider"],
        options.get("--workload") or workloads.DEFAULT_WORKLOAD_ID,
        "--debug" in options,
    )


def _check_cloud_db_url(raw_url: str) -> str | None:
    """Returns None if raw_url is a valid cloud-approved database URL, else an error.

    For non-local origins the URL must be explicitly configured as PostgreSQL.
    SQLite URLs (any form, including absolute paths and :memory:), empty values,
    and unsupported schemes are all rejected: they may resolve to ephemeral storage
    that disappears on container exit.

    Returns:
        None when the URL passes; a short, credential-free error message otherwise.
        Never echoes the URL value.
    """
    if not raw_url:
        return f"{config.DATABASE_URL_VARIABLE} is not set or is empty."
    # A URL without "://" is a bare path (absolute, relative, or :memory:);
    # treat it the same as sqlite since it cannot be a durable remote database.
    scheme = raw_url.split("://")[0] if "://" in raw_url else ""
    if not scheme or scheme == "sqlite":
        return (
            f"{config.DATABASE_URL_VARIABLE} is a SQLite URL or bare path,"
            " which is not durable for cloud-origin paid requests."
        )
    if scheme not in _CLOUD_APPROVED_DB_SCHEMES:
        return (
            f"{config.DATABASE_URL_VARIABLE} has an unsupported scheme."
            " Expected postgresql or postgresql+psycopg2."
        )
    return None


def _check_gcs_mode(
    target: targets.RequestProfile, origin: tuple[str, str]
) -> tuple[object_results.ResultTarget | None, str | None]:
    """Validates GCS-mode scope and target without any network access.

    Returns:
        (results_target, None) when GCS mode may proceed, else (None, a short
        error message that echoes no configured value).
    """
    if origin[0] != _GCS_ORIGIN_CLOUD:
        return None, (
            f"GCS results mode requires {config.ORIGIN_CLOUD_VARIABLE}="
            f"{_GCS_ORIGIN_CLOUD!r}."
        )
    if target.profile_id != _GCS_PROFILE_ID:
        return None, "GCS results mode supports only the OpenAI target."
    try:
        return object_results.target_from_environ(os.environ), None
    except object_results.TargetConfigError as e:
        return None, (
            f"{e} Set {object_results.RESULTS_BUCKET_VARIABLE} and"
            f" {object_results.RESULTS_PREFIX_VARIABLE}."
        )


def _now() -> str:
    return storage.format_timestamp(
        datetime.datetime.now(datetime.timezone.utc)
    )


def announce(
    target: targets.RequestProfile,
    workload: workloads.Workload,
    origin: tuple[str, str],
    price: pricing.Price,
) -> None:
    """Prints the safe pre-request announcement (no key, prompt or URL)."""
    source, verified_on = pricing.PRICE_PROVENANCE[
        (target.provider, target.model)
    ]
    print("About to make exactly ONE paid API request:")
    print(f"  Provider: {target.provider}")
    print(f"  Model: {target.model}")
    print(f"  Request profile: {target.profile_id}")
    print(f"  Endpoint: {target.endpoint}")
    print(f"  Reasoning/thinking: {target.reasoning}")
    print(f"  Cache policy: {target.cache_policy}")
    print(
        f"  Workload: {workload.workload_id} (about"
        f" {workload.target_input_tokens} input tokens estimated; max output"
        f" tokens {workload.max_output_tokens})"
    )
    print(f"  Origin: {origin[0]} / {origin[1]}")
    print(
        f"  Rates: ${price.input_per_1m:.2f} input / ${price.output_per_1m:.2f}"
        f" output per 1M tokens ({source}, verified {verified_on})"
    )
    if verified_on is None:
        print("Warning: the price for this model is not yet verified.")


def _print_diagnostics(diagnostics: dict[str, str]) -> None:
    details = ", ".join(f"{k}={v}" for k, v in diagnostics.items()) or "(none)"
    print(f"Debug (sanitized, not stored): {details}", file=sys.stderr)


def run(
    target: targets.RequestProfile,
    workload: workloads.Workload,
    debug: bool,
    *,
    store_factory=object_results.GcsObjectStore,
) -> int:
    """Makes one paid attempt of `workload` against `target` and saves it.

    Shared by this command and `real_smoke`. Every configuration refusal
    (invalid origin or backend, GCS scope/target, unpriced target, missing
    key, a workload `measure_attempt` refuses) happens before any network
    access; in GCS mode the storage preflight is the only network access
    before the paid request.

    Args:
        store_factory: Builds the GCS `ObjectStore` (GCS mode only); tests
            inject a fake.

    Returns:
        Process exit code: 0 when the attempt was recorded (successful or
        failed: a failure is a valid benchmark result), 2 when nothing was
        requested or the provider rejected the request itself (key, access,
        parameters, billing), in which case nothing is recorded, and 3 (GCS
        mode) when a request was made but its record is not confirmed durable.
    """
    try:
        origin = config.get_origin()
        backend = config.get_results_backend()
        price = pricing.price_for(target.provider, target.model)
    except (KeyError, config.ConfigError) as e:
        message = e.args[0] if isinstance(e, KeyError) else e
        print(f"Error: {message} No request was made.", file=sys.stderr)
        return 2

    if backend == "gcs":
        results_target, gcs_error = _check_gcs_mode(target, origin)
        if gcs_error:
            print(f"Error: {gcs_error} No request was made.", file=sys.stderr)
            return 2
        api_key = os.environ.get(target.api_key_variable, "")
        if not api_key:
            print(
                f"Error: {target.api_key_variable} is not set. No request was"
                " made.",
                file=sys.stderr,
            )
            return 2
        return _run_gcs(
            target, workload, debug, origin, price, api_key, results_target,
            store_factory,
        )  # fmt: skip

    # Cloud-origin guard: before reading the API key or constructing any
    # provider adapter. Rejects non-PostgreSQL database configurations for
    # non-local origins so a paid request never silently falls back to ephemeral
    # container SQLite. Origin is operator-declared and not cryptographically
    # attested; this is a configuration safety gate, not proof of durability.
    # Local origin retains existing SQLite behavior (intentional for local dev).
    if origin[0] != config.DEFAULT_ORIGIN_CLOUD:
        raw_url = os.environ.get(config.DATABASE_URL_VARIABLE, "")
        url_error = _check_cloud_db_url(raw_url)
        if url_error:
            print(
                f"Error: {config.ORIGIN_CLOUD_VARIABLE}={origin[0]!r}:"
                f" {url_error} Cloud-origin paid requests require an explicit"
                f" PostgreSQL {config.DATABASE_URL_VARIABLE} to prevent data"
                " loss to ephemeral container storage. No request was made.",
                file=sys.stderr,
            )
            return 2

    api_key = os.environ.get(target.api_key_variable, "")
    if not api_key:
        print(
            f"Error: {target.api_key_variable} is not set. No request was"
            " made.\nSet it in your shell (never commit it), e.g.:"
            f" export {target.api_key_variable}=...",
            file=sys.stderr,
        )
        return 2

    db_path = config.get_database_url()
    # Pre-flight: verify DB is reachable and schema is ready before making a
    # paid API call. A storage failure after the call would orphan a billed
    # attempt. This runs before the announcement so "No request was made" is
    # always accurate.
    try:
        storage.connect(db_path)
    except Exception:  # pylint: disable=broad-except
        print(
            "Error: cannot connect to the database before making a paid"
            f" request ({storage._redact_db_url(str(db_path))})."
            " Check DB availability. No request was made.",
            file=sys.stderr,
        )
        return 2

    provider = ADAPTERS[target.provider](api_key)
    announce(target, workload, origin, price)
    print()

    try:
        request, results, request_id = benchmark.run_attempt(
            provider, workload, ENVIRONMENT, db_path, origin=origin
        )
    except http_streaming.RequestRejected as e:
        print(
            f"Error: {e} Check the API key, account access and billing, model"
            " name, and request parameters. Nothing was recorded.",
            file=sys.stderr,
        )
        if debug:
            _print_diagnostics(e.diagnostics)
        return 2
    except ValueError as e:
        # Refused by run_attempt's checks, which run before the request.
        print(f"Error: {e} No request was made.", file=sys.stderr)
        return 2
    benchmark.print_summary(
        request, results, request_id, db_path, simulated=False
    )
    if debug and request["outcome"] != "success":
        _print_diagnostics(request.get("diagnostics", {}))
    return 0


def _run_gcs(
    target: targets.RequestProfile,
    workload: workloads.Workload,
    debug: bool,
    origin: tuple[str, str],
    price: pricing.Price,
    api_key: str,
    results_target: object_results.ResultTarget,
    store_factory,
) -> int:
    """GCS mode of `run`: preflight, one request, one immutable record."""
    location = f"gs://{results_target.bucket}/{results_target.prefix}/"
    # Real capability check before any paid request. Failures (including
    # missing credentials while building the client) print only the error
    # class, never messages that could carry transport or credential detail.
    try:
        store = store_factory()
        probe = object_results.preflight(
            store, results_target, probe_id=uuid.uuid4().hex, now=_now()
        )
    except Exception as e:  # pylint: disable=broad-except
        print(
            f"Error: GCS results preflight failed ({type(e).__name__}) for"
            f" {location}. No request was made.",
            file=sys.stderr,
        )
        return 2
    provider = ADAPTERS[target.provider](api_key)
    # Fixed before the request, so a billed attempt whose record cannot be
    # written is still identifiable in the job output.
    attempt_id = uuid.uuid4().hex
    announce(target, workload, origin, price)
    print(f"  Attempt id: {attempt_id}")
    print(f"  Results: {location} (GCS, create-only; preflight {probe})")
    print()

    try:
        request, results = benchmark.measure_attempt(
            provider, workload, origin=origin
        )
    except http_streaming.RequestRejected as e:
        print(
            f"Error: {e} Check the API key, account access and billing, model"
            " name, and request parameters. Nothing was recorded.",
            file=sys.stderr,
        )
        if debug:
            _print_diagnostics(e.diagnostics)
        return 2
    except ValueError as e:
        print(f"Error: {e} No request was made.", file=sys.stderr)
        return 2

    # Exactly one write attempt sequence (bounded storage retries inside
    # write_record). The provider request is never repeated, and the record
    # payload is never printed: it is either durable in GCS or reported lost.
    try:
        record = object_results.build_record(
            request,
            results,
            ENVIRONMENT,
            attempt_id=attempt_id,
            recorded_at=_now(),
        )
        written = object_results.write_record(store, results_target, record)
    except object_results.ResultStoreError as e:
        print(
            f"Error: attempt {attempt_id} was requested (outcome"
            f" {request['outcome']}) but its record is NOT confirmed durable"
            f" ({type(e).__name__}: {e}). The provider request will not be"
            " retried.",
            file=sys.stderr,
        )
        return EXIT_NOT_PERSISTED
    benchmark.print_summary(
        request,
        results,
        attempt_id,
        f"gs://{results_target.bucket}/{written.name}",
        simulated=False,
    )
    state = "created" if written.created else "identical object already present"
    print(f"Record sha256: {written.sha256} ({state})")
    if debug and request["outcome"] != "success":
        _print_diagnostics(request.get("diagnostics", {}))
    return 0


def main(argv: list[str] | None = None) -> int:
    """Runs the command; see `run` for the exit codes.

    Args:
        argv: Command-line arguments without the program name; defaults to
            `sys.argv[1:]`.
    """
    try:
        provider_name, workload_id, debug = _parse_args(
            sys.argv[1:] if argv is None else argv
        )
        target = targets.get_target(provider_name)
        workload = workloads.get_workload(workload_id)
    except ValueError as e:
        print(f"Error: {e} No request was made.", file=sys.stderr)
        return 2
    return run(target, workload, debug)


if __name__ == "__main__":
    sys.exit(main())
