"""CLI: measure TTFT, total latency, and output throughput for one request.

Usage: APP_ENV=test python -m llm_metrics
"""

import os
import sys

from llm_metrics.config import ConfigError, get_app_env, get_db_path, get_provider
from llm_metrics.latency import METRICS, measure_request
from llm_metrics.storage import save_observations

PROMPT = "Say hello."


def main() -> int:
    try:
        app_env = get_app_env()
        provider = get_provider(app_env)
    except ConfigError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    results = measure_request(provider, PROMPT)
    print(f"Provider: {results[0]['provider']}")
    print(f"Model: {results[0]['model']}")
    for result in results:
        label, unit = METRICS[result["metric"]]
        print(f"{label}: {result['value']:.1f} {unit}")
    if not any(r["metric"] == "output_chunks_per_s" for r in results):
        print("Output throughput: not recorded (fewer than 2 output chunks)")

    db_path = get_db_path()
    save_observations(db_path, results, app_env)
    print(f"Saved {len(results)} observations to {os.path.relpath(db_path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
