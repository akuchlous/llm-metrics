"""CLI: make one simulated benchmark attempt and save it. Never calls a paid API.

Usage: APP_ENV=test python -m llm_metrics
(For one real request, see python -m llm_metrics.real_smoke.)
"""

import sys

from llm_metrics.benchmark import print_summary, run_attempt
from llm_metrics.config import ConfigError, get_app_env, get_db_path, get_provider

PROMPT = "Say hello."
MAX_OUTPUT_TOKENS = 64  # requested output cap for each benchmark request


def main() -> int:
    try:
        app_env = get_app_env()
        provider = get_provider(app_env)
    except ConfigError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    db_path = get_db_path()
    request, results, request_id = run_attempt(provider, PROMPT, MAX_OUTPUT_TOKENS, app_env, db_path)
    print_summary(request, results, request_id, db_path, simulated=app_env == "test")
    # A failed attempt is still a successfully recorded benchmark result.
    return 0


if __name__ == "__main__":
    sys.exit(main())
