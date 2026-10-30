"""Make exactly ONE real, paid benchmark request to OpenAI and save it.

Usage: OPENAI_API_KEY=... python -m llm_metrics.real_smoke [--debug]

--debug prints sanitized failure diagnostics to stderr (which code path failed,
HTTP status, OpenAI request id, error code/type/param, incomplete reason). They
are never stored, and never include the key, prompt, response text, headers, or
provider error messages or bodies.

This is the only code path that calls a paid API, and it runs only when invoked
explicitly. It makes one attempt (no retries, no loop), stores it with
environment 'prod' (real data, kept apart from simulated 'test' data), and
prints a summary. It never prints the API key, the prompt, or the response.
"""

import os
import sys

from llm_metrics.benchmark import print_summary, run_attempt
from llm_metrics.config import ConfigError, get_db_path, get_origin
from llm_metrics.openai_provider import OpenAIProvider, RequestRejected
from llm_metrics.pricing import PRICE_PROVENANCE

API_KEY_VARIABLE = "OPENAI_API_KEY"
MODEL = "gpt-6-luna"
# The smoke benchmark case: this prompt, cap, and request shape (streaming,
# store false, reasoning effort none, prompt caching disabled). Change the
# version if any of them changes. (v1: the same without the cache control.)
WORKLOAD_ID = "smoke.short_text.v2"
# Harmless, deterministic, text-only; no tools, files, images, or search.
PROMPT = "Reply with one short friendly sentence greeting a benchmark tool."
MAX_OUTPUT_TOKENS = 64
ENVIRONMENT = "prod"


def _print_diagnostics(diagnostics: dict) -> None:
    details = ", ".join(f"{k}={v}" for k, v in diagnostics.items()) or "(none)"
    print(f"Debug (sanitized, not stored): {details}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args not in ([], ["--debug"]):
        print("Usage: python -m llm_metrics.real_smoke [--debug]", file=sys.stderr)
        return 2
    debug = args == ["--debug"]
    api_key = os.environ.get(API_KEY_VARIABLE, "")
    if not api_key:
        print(
            f"Error: {API_KEY_VARIABLE} is not set. No request was made.\n"
            f"Set it in your shell (never commit it), e.g.: export {API_KEY_VARIABLE}=...",
            file=sys.stderr,
        )
        return 2

    try:
        origin = get_origin()
    except ConfigError as e:
        print(f"Error: {e} No request was made.", file=sys.stderr)
        return 2

    provider = OpenAIProvider(api_key, model=MODEL)
    source, verified_on = PRICE_PROVENANCE[(provider.name, provider.model)]
    print(f"About to make exactly ONE paid API request: provider {provider.name}, "
          f"model {provider.model}, max output tokens {MAX_OUTPUT_TOKENS}.")
    if verified_on is None:
        print(f"Warning: the price for this model is not yet verified against {source}.")
    print()

    db_path = get_db_path()
    try:
        request, results, request_id = run_attempt(
            provider, PROMPT, MAX_OUTPUT_TOKENS, ENVIRONMENT, db_path,
            workload_id=WORKLOAD_ID, origin=origin,
        )
    except RequestRejected as e:
        print(f"Error: {e} Check the API key, account access, model name, and request "
              "parameters. Nothing was recorded.", file=sys.stderr)
        if debug:
            _print_diagnostics(e.diagnostics)
        return 2
    print_summary(request, results, request_id, db_path, simulated=False)
    if debug and request["outcome"] != "success":
        _print_diagnostics(request.get("diagnostics", {}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
