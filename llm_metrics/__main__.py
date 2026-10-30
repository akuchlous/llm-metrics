# Python requires this file name for `python -m llm_metrics`.
# pylint: disable=invalid-name
"""CLI: makes one simulated benchmark attempt and saves it.

Usage: APP_ENV=test python -m llm_metrics

This path never calls a paid API: `APP_ENV=prod` is refused by
`config.get_provider`. The only real-provider path is
`python -m llm_metrics.real_smoke`.
"""

import sys

from llm_metrics import benchmark
from llm_metrics import config

# The simulated benchmark case (what was run). Bump the version whenever the
# prompt, the output cap, or the request shape changes, so attempts with
# different conditions never share an id.
WORKLOAD_ID = "simulated.default.v1"
PROMPT = "Say hello."
MAX_OUTPUT_TOKENS = 64  # Requested output cap for each benchmark request.


def main() -> int:
    """Runs one simulated attempt, prints its summary, and saves it.

    Returns:
        Process exit code: 0 when the attempt was recorded (even if the attempt
        itself failed, because a failure is a valid benchmark result), 2 for a
        configuration error, in which case nothing is measured or saved.
    """
    try:
        app_env = config.get_app_env()
        provider = config.get_provider(app_env)
        origin = config.get_origin()
    except config.ConfigError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    db_path = config.get_db_path()
    request, results, request_id = benchmark.run_attempt(
        provider,
        PROMPT,
        MAX_OUTPUT_TOKENS,
        app_env,
        db_path,
        workload_id=WORKLOAD_ID,
        origin=origin,
    )
    benchmark.print_summary(
        request, results, request_id, db_path, simulated=app_env == "test"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
