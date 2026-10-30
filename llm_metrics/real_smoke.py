"""Makes exactly ONE real, paid benchmark request to OpenAI and saves it.

Usage: OPENAI_API_KEY=... python -m llm_metrics.real_smoke [--debug]

This is the only code path that calls a paid API, and it runs only when
invoked explicitly. It makes one attempt (no retries, no loop), stores it with
environment "prod" (real data, kept apart from simulated "test" data), and
prints a summary. It never prints the API key, the prompt, or the response.

`--debug` prints sanitized failure diagnostics to stderr: which code path
failed, HTTP status, OpenAI request id, error code/type/param, and incomplete
reason. They are never stored and never include the key, prompt, response
text, headers, or provider error messages or bodies.
"""

import os
import sys

from llm_metrics import benchmark
from llm_metrics import config
from llm_metrics import openai_provider
from llm_metrics import pricing

API_KEY_VARIABLE = "OPENAI_API_KEY"
MODEL = "gpt-6-luna"
# The smoke benchmark case: this prompt, cap, and request shape (streaming,
# store false, reasoning effort none, prompt caching disabled). Bump the
# version whenever any of them changes, so attempts made under different
# conditions never share an id.
WORKLOAD_ID = "smoke.short_text.v2"
# Harmless, deterministic, text-only; no tools, files, images, or search.
PROMPT = "Reply with one short friendly sentence greeting a benchmark tool."
MAX_OUTPUT_TOKENS = 64
ENVIRONMENT = "prod"


def _print_diagnostics(diagnostics: dict[str, str]) -> None:
    details = ", ".join(f"{k}={v}" for k, v in diagnostics.items()) or "(none)"
    print(f"Debug (sanitized, not stored): {details}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    """Runs the smoke command.

    Every refusal (bad arguments, missing key, invalid origin) happens before
    any request is made.

    Args:
        argv: Command-line arguments without the program name; defaults to
            `sys.argv[1:]`. Only `[]` and `["--debug"]` are accepted.

    Returns:
        Process exit code: 0 when the attempt was recorded (successful or
        failed), 2 when nothing was requested or OpenAI rejected the request
        itself (bad key, access, parameters, or account credit), in which case
        nothing is recorded.
    """
    args = sys.argv[1:] if argv is None else argv
    if args not in ([], ["--debug"]):
        print(
            "Usage: python -m llm_metrics.real_smoke [--debug]", file=sys.stderr
        )
        return 2
    debug = args == ["--debug"]
    api_key = os.environ.get(API_KEY_VARIABLE, "")
    if not api_key:
        print(
            f"Error: {API_KEY_VARIABLE} is not set. No request was made.\n"
            "Set it in your shell (never commit it), e.g.:"
            f" export {API_KEY_VARIABLE}=...",
            file=sys.stderr,
        )
        return 2

    try:
        origin = config.get_origin()
    except config.ConfigError as e:
        print(f"Error: {e} No request was made.", file=sys.stderr)
        return 2

    provider = openai_provider.OpenAIProvider(api_key, model=MODEL)
    source, verified_on = pricing.PRICE_PROVENANCE[
        (provider.name, provider.model)
    ]
    print(
        "About to make exactly ONE paid API request: provider"
        f" {provider.name}, model {provider.model}, max output tokens"
        f" {MAX_OUTPUT_TOKENS}."
    )
    if verified_on is None:
        print(
            "Warning: the price for this model is not yet verified against"
            f" {source}."
        )
    print()

    db_path = config.get_db_path()
    try:
        request, results, request_id = benchmark.run_attempt(
            provider,
            PROMPT,
            MAX_OUTPUT_TOKENS,
            ENVIRONMENT,
            db_path,
            workload_id=WORKLOAD_ID,
            origin=origin,
        )
    except openai_provider.RequestRejected as e:
        print(
            f"Error: {e} Check the API key, account access, model name, and"
            " request parameters. Nothing was recorded.",
            file=sys.stderr,
        )
        if debug:
            _print_diagnostics(e.diagnostics)
        return 2
    benchmark.print_summary(
        request, results, request_id, db_path, simulated=False
    )
    if debug and request["outcome"] != "success":
        _print_diagnostics(request.get("diagnostics", {}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
