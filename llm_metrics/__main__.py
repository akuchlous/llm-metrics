"""CLI: make one benchmark attempt (outcome, tokens, latency, throughput, cost) and save it.

Usage: APP_ENV=test python -m llm_metrics
"""

import os
import sys

from llm_metrics.config import ConfigError, get_app_env, get_db_path, get_provider
from llm_metrics.latency import METRICS, measure_request
from llm_metrics.outcomes import FAILURE_CATEGORIES, SUCCESS
from llm_metrics.pricing import price_for, request_cost
from llm_metrics.storage import save_request

PROMPT = "Say hello."
MAX_OUTPUT_TOKENS = 64  # requested output cap for each benchmark request


def main() -> int:
    try:
        app_env = get_app_env()
        provider = get_provider(app_env)
    except ConfigError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    attempt, results = measure_request(provider, PROMPT, MAX_OUTPUT_TOKENS)
    price = price_for(attempt["provider"], attempt["model"])
    if attempt["outcome"] == SUCCESS:
        cost = request_cost(attempt["input_tokens"], attempt["output_tokens"], price)
    else:  # unknown, not zero
        cost = {"input_cost": None, "output_cost": None, "total_cost": None}
    request = {
        **attempt,
        "input_price_per_1m": price.input_per_1m,
        "output_price_per_1m": price.output_per_1m,
        **cost,
    }

    simulated = " (simulated)" if app_env == "test" else ""
    print(f"Provider: {request['provider']}")
    print(f"Model: {request['model']}")
    if request["outcome"] == SUCCESS:
        print("Outcome: success")
        for result in results:
            label, unit = METRICS[result["metric"]]
            print(f"{label}: {result['value']:.1f} {unit}")
        if not any(r["metric"] == "output_chunks_per_s" for r in results):
            print("Output throughput: not recorded (fewer than 2 output chunks)")
        print(f"Input tokens: {request['input_tokens']}{simulated}")
        print(
            f"Output tokens: {request['output_tokens']} of max "
            f"{request['requested_max_output_tokens']}{simulated}"
        )
        print(
            f"Cost: ${request['total_cost']:.6f} (input ${request['input_cost']:.6f}"
            f" + output ${request['output_cost']:.6f}){simulated}"
        )
    else:
        label = FAILURE_CATEGORIES[request["outcome"]]
        print(f"Outcome: FAILED — {label} ({request['outcome']})")
        print(f"Failed after: {request['failed_after_ms']:.1f} ms")
        print("Tokens, cost, latency, and throughput: unknown (not recorded)")

    db_path = get_db_path()
    request_id = save_request(db_path, request, results, app_env)
    print(
        f"Saved attempt {request_id} with {len(results)} observations "
        f"to {os.path.relpath(db_path)}"
    )
    # A failed attempt is still a successfully recorded benchmark result.
    return 0


if __name__ == "__main__":
    sys.exit(main())
