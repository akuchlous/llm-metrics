"""One benchmark attempt end to end: price, measure, save, and summarize.

Shared by the simulated CLI (`python -m llm_metrics`) and the real-provider
smoke command (`python -m llm_metrics.real_smoke`), so both record attempts the
same way. Never prints the prompt or the model's response.
"""

import os
import pathlib

from llm_metrics import latency
from llm_metrics import outcomes
from llm_metrics import pricing
from llm_metrics import providers
from llm_metrics import storage


def run_attempt(
    provider: providers.LLMProvider,
    prompt: str,
    max_output_tokens: int,
    environment: str,
    db_path: pathlib.Path,
    *,
    workload_id: str,
    origin: tuple[str, str],
) -> tuple[dict, list[dict], str]:
    """Makes one attempt and saves it with its conditions and cost.

    The price is looked up before the provider is called, so a missing price
    never wastes a paid request. The provider's declared cache policy is stored
    as-is, so it always matches the request that was sent.

    Args:
        provider: Provider to call exactly once.
        prompt: Prompt text; never stored or printed.
        max_output_tokens: Output cap requested from the provider.
        environment: "test" (simulated data) or "prod" (real-provider data).
        db_path: SQLite database to write to.
        workload_id: Stable id of the benchmark case that was run, e.g.
            "smoke.short_text.v2".
        origin: (origin_cloud, origin_region) of this runner; see
            `config.get_origin`.

    Returns:
        (request, results, request_id): the saved request facts (including the
        unsaved "diagnostics" of a failure), the metric observations, and the
        new request's id.

    Raises:
        ValueError: If the provider declares cache policy "unknown" or a value
            outside `providers.CACHE_POLICIES`; nothing is called or saved.
        KeyError: If no price is defined for the provider/model.
    """
    if (
        provider.cache_policy not in providers.CACHE_POLICIES
        or provider.cache_policy == "unknown"
    ):
        raise ValueError(
            "Provider cache_policy must be one of"
            f" {providers.CACHE_POLICIES[:3]}."
        )
    price = pricing.price_for(provider.name, provider.model)
    attempt, results = latency.measure_request(
        provider, prompt, max_output_tokens
    )
    if attempt["outcome"] == outcomes.SUCCESS:
        cost = pricing.request_cost(
            attempt["input_tokens"], attempt["output_tokens"], price
        )
    else:
        # A failed attempt's cost is unknown (it may or may not have been
        # billed), never zero.
        cost = {"input_cost": None, "output_cost": None, "total_cost": None}
    origin_cloud, origin_region = origin
    request = {
        **attempt,
        "workload_id": workload_id,
        "origin_cloud": origin_cloud,
        "origin_region": origin_region,
        "cache_policy": provider.cache_policy,
        "input_price_per_1m": price.input_per_1m,
        "output_price_per_1m": price.output_per_1m,
        **cost,
    }
    request_id = storage.save_request(db_path, request, results, environment)
    return request, results, request_id


def print_summary(
    request: dict,
    results: list[dict],
    request_id: str,
    db_path: pathlib.Path,
    simulated: bool,
) -> None:
    """Prints a human-readable summary of one saved attempt to stdout.

    Args:
        request: Request facts as returned by `run_attempt`.
        results: Metric observations as returned by `run_attempt`.
        request_id: The saved request's id.
        db_path: Database the attempt was saved to (shown relative).
        simulated: Whether to mark token counts, costs and rates as simulated.
    """
    note = " (simulated)" if simulated else ""
    print(f"Provider: {request['provider']}")
    print(f"Model: {request['model']}")
    print(f"Workload: {request['workload_id']}")
    print(f"Origin: {request['origin_cloud']} / {request['origin_region']}")
    print(f"Cache policy: {request['cache_policy']}")
    if request["outcome"] == outcomes.SUCCESS:
        print("Outcome: success")
        for result in results:
            label, unit = latency.METRICS[result["metric"]]
            print(f"{label}: {result['value']:.1f} {unit}")
        if not any(r["metric"] == "output_chunks_per_s" for r in results):
            print(
                "Output throughput: not recorded (fewer than 2 output chunks)"
            )
        print(f"Input tokens: {request['input_tokens']}{note}")
        cached = request["cached_input_tokens"]
        cached_text = "not reported" if cached is None else cached
        print(f"Cached input tokens: {cached_text}")
        print(
            f"Output tokens: {request['output_tokens']} of max "
            f"{request['requested_max_output_tokens']}{note}"
        )
        print(
            f"Cost: ${request['total_cost']:.6f}"
            f" (input ${request['input_cost']:.6f}"
            f" + output ${request['output_cost']:.6f}){note}"
        )
    else:
        label = outcomes.FAILURE_CATEGORIES[request["outcome"]]
        print(f"Outcome: FAILED — {label} ({request['outcome']})")
        print(f"Failed after: {request['failed_after_ms']:.1f} ms")
        print(
            "Requested max output tokens:"
            f" {request['requested_max_output_tokens']}"
        )
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
