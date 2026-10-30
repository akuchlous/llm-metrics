"""One benchmark attempt end to end: measure, price, save, summarize.

Shared by the simulated CLI (python -m llm_metrics) and the real-provider smoke
command (python -m llm_metrics.real_smoke). Never prints the prompt or the
model's response.
"""

import os
from pathlib import Path

from llm_metrics.latency import METRICS, measure_request
from llm_metrics.outcomes import FAILURE_CATEGORIES, SUCCESS
from llm_metrics.pricing import price_for, request_cost
from llm_metrics.providers import LLMProvider
from llm_metrics.storage import save_request


def run_attempt(
    provider: LLMProvider, prompt: str, max_output_tokens: int, environment: str, db_path: Path,
    *, workload_id: str, origin: tuple[str, str],
) -> tuple[dict, list[dict], str]:
    """Make one attempt and save it; return (request, results, request_id).

    `workload_id` names the benchmark case (what was run); `origin` is
    (origin_cloud, origin_region) of this runner (see config.get_origin). Both
    are stored with the attempt. The price is looked up before the call, so a
    missing price never wastes a paid request.
    """
    price = price_for(provider.name, provider.model)
    attempt, results = measure_request(provider, prompt, max_output_tokens)
    if attempt["outcome"] == SUCCESS:
        cost = request_cost(attempt["input_tokens"], attempt["output_tokens"], price)
    else:  # unknown, not zero
        cost = {"input_cost": None, "output_cost": None, "total_cost": None}
    origin_cloud, origin_region = origin
    request = {
        **attempt,
        "workload_id": workload_id,
        "origin_cloud": origin_cloud,
        "origin_region": origin_region,
        "input_price_per_1m": price.input_per_1m,
        "output_price_per_1m": price.output_per_1m,
        **cost,
    }
    request_id = save_request(db_path, request, results, environment)
    return request, results, request_id


def print_summary(request: dict, results: list[dict], request_id: str, db_path: Path,
                  simulated: bool) -> None:
    note = " (simulated)" if simulated else ""
    print(f"Provider: {request['provider']}")
    print(f"Model: {request['model']}")
    print(f"Workload: {request['workload_id']}")
    print(f"Origin: {request['origin_cloud']} / {request['origin_region']}")
    if request["outcome"] == SUCCESS:
        print("Outcome: success")
        for result in results:
            label, unit = METRICS[result["metric"]]
            print(f"{label}: {result['value']:.1f} {unit}")
        if not any(r["metric"] == "output_chunks_per_s" for r in results):
            print("Output throughput: not recorded (fewer than 2 output chunks)")
        print(f"Input tokens: {request['input_tokens']}{note}")
        print(
            f"Output tokens: {request['output_tokens']} of max "
            f"{request['requested_max_output_tokens']}{note}"
        )
        print(
            f"Cost: ${request['total_cost']:.6f} (input ${request['input_cost']:.6f}"
            f" + output ${request['output_cost']:.6f}){note}"
        )
    else:
        label = FAILURE_CATEGORIES[request["outcome"]]
        print(f"Outcome: FAILED — {label} ({request['outcome']})")
        print(f"Failed after: {request['failed_after_ms']:.1f} ms")
        print(f"Requested max output tokens: {request['requested_max_output_tokens']}")
        print("Tokens, cost, latency, and throughput: unknown (not recorded)")
    if request.get("provider_request_id"):
        print(f"Provider request id: {request['provider_request_id']}")
    print(
        f"Rates: ${request['input_price_per_1m']:.2f} input / "
        f"${request['output_price_per_1m']:.2f} output per 1M tokens{note}"
    )
    print(
        f"Saved attempt {request_id} with {len(results)} observations "
        f"to {os.path.relpath(db_path)}"
    )
