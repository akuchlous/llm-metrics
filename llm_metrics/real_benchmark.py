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
"""

import os
import sys

from llm_metrics import anthropic_provider
from llm_metrics import benchmark
from llm_metrics import config
from llm_metrics import google_provider
from llm_metrics import http_streaming
from llm_metrics import openai_provider
from llm_metrics import pricing
from llm_metrics import targets
from llm_metrics import workloads
from llm_metrics import xai_provider

USAGE = (
    "Usage: python -m llm_metrics.real_benchmark --provider PROVIDER --real"
    " [--workload WORKLOAD_ID] [--debug]"
)
ENVIRONMENT = "prod"
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


def _print_diagnostics(diagnostics: dict[str, str]) -> None:
    details = ", ".join(f"{k}={v}" for k, v in diagnostics.items()) or "(none)"
    print(f"Debug (sanitized, not stored): {details}", file=sys.stderr)


def run(
    target: targets.RequestProfile, workload: workloads.Workload, debug: bool
) -> int:
    """Makes one paid attempt of `workload` against `target` and saves it.

    Shared by this command and `real_smoke`. Every refusal (invalid origin,
    unpriced target, missing key, a workload `run_attempt` refuses) happens
    before any network access.

    Returns:
        Process exit code: 0 when the attempt was recorded (successful or
        failed: a failure is a valid benchmark result), 2 when nothing was
        requested or the provider rejected the request itself (key, access,
        parameters, billing), in which case nothing is recorded.
    """
    try:
        origin = config.get_origin()
        price = pricing.price_for(target.provider, target.model)
    except (KeyError, config.ConfigError) as e:
        message = e.args[0] if isinstance(e, KeyError) else e
        print(f"Error: {message} No request was made.", file=sys.stderr)
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

    provider = ADAPTERS[target.provider](api_key)
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
    print()

    db_path = config.get_database_url()
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
