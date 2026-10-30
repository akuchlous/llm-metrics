"""CLI: run one TTFT measurement. Usage: APP_ENV=test python -m llm_metrics"""

import os
import sys

from llm_metrics.config import ConfigError, get_app_env, get_db_path, get_provider
from llm_metrics.storage import save_observation
from llm_metrics.ttft import measure_ttft

PROMPT = "Say hello."


def main() -> int:
    try:
        app_env = get_app_env()
        provider = get_provider(app_env)
    except ConfigError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    result = measure_ttft(provider, PROMPT)
    print(f"Provider: {result['provider']}")
    print(f"Model: {result['model']}")
    print("Metric: TTFT")
    print(f"TTFT: {result['value_ms']:.1f} ms")

    db_path = get_db_path()
    save_observation(db_path, result, app_env)
    print(f"Saved observation to {os.path.relpath(db_path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
