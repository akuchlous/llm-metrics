"""CLI: measure TTFT and total latency for one request. Usage: APP_ENV=test python -m llm_metrics"""

import os
import sys

from llm_metrics.config import ConfigError, get_app_env, get_db_path, get_provider
from llm_metrics.latency import measure_latency
from llm_metrics.storage import save_observations

PROMPT = "Say hello."


def main() -> int:
    try:
        app_env = get_app_env()
        provider = get_provider(app_env)
    except ConfigError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    ttft, total = measure_latency(provider, PROMPT)
    print(f"Provider: {ttft['provider']}")
    print(f"Model: {ttft['model']}")
    print(f"TTFT: {ttft['value_ms']:.1f} ms")
    print(f"Total latency: {total['value_ms']:.1f} ms")

    db_path = get_db_path()
    save_observations(db_path, [ttft, total], app_env)
    print(f"Saved 2 observations to {os.path.relpath(db_path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
