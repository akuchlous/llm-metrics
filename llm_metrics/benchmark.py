"""One benchmark attempt end to end: price, measure, save, and summarize.

Shared by the simulated CLI (`python -m llm_metrics`) and the real-provider
smoke command (`python -m llm_metrics.real_smoke`), so both record attempts the
same way. Never prints the prompt or the model's response.

Dependency direction: workloads (what to send) and targets (to whom, under
which request settings) -> benchmark (this module: runs one workload once) ->
latency/providers (timing and protocol) -> storage (facts). The workload's
prompt is sent but never stored; its versioned id is, and so is the provider's
request profile id.
"""

import os
import pathlib

from llm_metrics import latency
from llm_metrics import outcomes
from llm_metrics import pricing
from llm_metrics import providers
from llm_metrics import storage
from llm_metrics import targets
from llm_metrics import workloads


def run_attempt(
    provider: providers.LLMProvider,
    workload: workloads.Workload,
    environment: str,
    db_ref: pathlib.Path | str,
    *,
    origin: tuple[str, str],
) -> tuple[dict, list[dict], str]:
    """Runs one workload once and saves the attempt to SQL storage.

    `measure_attempt` followed by `storage.save_request`; see
    `measure_attempt` for the measurement, pricing and refusal contract.

    Args:
        provider: Provider to call exactly once.
        workload: A catalogue workload (`workloads.get_workload`).
        environment: "test" (simulated data) or "prod" (real-provider data).
        db_ref: Database to write to: a pathlib.Path for a local SQLite file,
            or a SQLAlchemy URL string (e.g. 'postgresql://host/db').
        origin: (origin_cloud, origin_region) of this runner.

    Returns:
        (request, results, request_id): the saved request facts (including the
        unsaved "diagnostics" of a failure), the metric observations, and the
        new request's id.

    Raises:
        ValueError, KeyError: As `measure_attempt`; nothing is called or saved.
    """
    request, results = measure_attempt(provider, workload, origin=origin)
    request_id = storage.save_request(db_ref, request, results, environment)
    return request, results, request_id


def measure_attempt(
    provider: providers.LLMProvider,
    workload: workloads.Workload,
    *,
    origin: tuple[str, str],
) -> tuple[dict, list[dict]]:
    """Runs one workload once and returns the attempt with its conditions.

    Persistence is the caller's: `run_attempt` saves to SQL storage, and the
    explicitly selected GCS mode of `real_benchmark` writes an immutable record.

    The provider receives the workload's prompt and output cap unchanged, and
    the attempt is stored under the workload's versioned id, so every stored
    id stands for exactly the content that was sent. One call is one attempt:
    nothing retries, and a response shorter than the cap is a valid result
    (the cap is a maximum, not a target).

    The attempt is stored with the provider's request profile id, so every
    stored measurement names the exact provider, model and request settings
    it was made under; a provider whose name, model or cache policy disagrees
    with its registered profile is refused, so populations cannot silently mix
    settings. The cache policy stored is the profile's.

    The price is looked up before the provider is called, so a missing price
    never wastes a paid request. Cost uses the provider-reported cached input
    tokens at the cached rate when reported, and the standard rates otherwise.

    Args:
        provider: Provider to call exactly once.
        workload: A catalogue workload (`workloads.get_workload`). Its prompt
            is never stored or printed.
        origin: (origin_cloud, origin_region) of this runner; see
            `config.get_origin`.

    Returns:
        (request, results): the request facts (every storage fact except the
        identity, plus the never-stored "diagnostics" of a failure) and the
        metric observations.

    Raises:
        ValueError: If `workload` is not the catalogue's definition of its id
            (so a stored id could not be trusted to mean that content); the
            provider has no registered request profile, or its name, model or
            cache policy differs from the profile's; or the workload is not
            well within the price's prompt-size tier. Nothing is called.
        KeyError: If no price is defined for the provider/model.
    """
    if workloads.get_workload(workload.workload_id) != workload:
        raise ValueError("Workload is not the catalogue definition of its id.")
    # Registered profiles only declare valid, known cache policies (tested in
    # tests/test_targets.py), so matching the profile also rules out
    # "unknown" or invented policies.
    profile = provider.request_profile
    if profile is None or targets.get_profile(profile.profile_id) != profile:
        raise ValueError("Provider has no registered request profile.")
    if (provider.name, provider.model, provider.cache_policy) != (
        profile.provider,
        profile.model,
        profile.cache_policy,
    ):
        raise ValueError("Provider does not match its request profile.")
    price = pricing.price_for(provider.name, provider.model)
    # Rates above the tier limit are not modelled. Provider token counts
    # differ from the workload's size estimate, so require a 2x margin.
    if (
        price.max_input_tokens is not None
        and workload.target_input_tokens * 2 > price.max_input_tokens
    ):
        raise ValueError("Workload is too large for the modelled price tier.")
    attempt, results = latency.measure_request(
        provider, workload.prompt, workload.max_output_tokens
    )
    if attempt["outcome"] == outcomes.SUCCESS:
        cost = pricing.request_cost(
            attempt["input_tokens"],
            attempt["output_tokens"],
            price,
            attempt["cached_input_tokens"],
        )
    else:
        # A failed attempt's cost is unknown (it may or may not have been
        # billed), never zero.
        cost = {"input_cost": None, "output_cost": None, "total_cost": None}
    origin_cloud, origin_region = origin
    request = {
        **attempt,
        "workload_id": workload.workload_id,
        "origin_cloud": origin_cloud,
        "origin_region": origin_region,
        "cache_policy": provider.cache_policy,
        "request_profile_id": profile.profile_id,
        "input_price_per_1m": price.input_per_1m,
        "output_price_per_1m": price.output_per_1m,
        "cached_input_price_per_1m": price.cached_input_per_1m,
        **cost,
    }
    return request, results


def _db_display(db_ref: pathlib.Path | str) -> str:
    """Returns a credential-safe, human-readable label for a database ref."""
    if isinstance(db_ref, pathlib.Path):
        return os.path.relpath(db_ref)
    s = str(db_ref)
    if s.startswith("sqlite:///"):
        return os.path.relpath(s[len("sqlite:///"):])
    at = s.find("@")
    if at >= 0:
        scheme_end = s.find("://")
        if scheme_end >= 0:
            return s[: scheme_end + 3] + s[at + 1 :]
    return s


def print_summary(
    request: dict,
    results: list[dict],
    request_id: str,
    db_ref: pathlib.Path | str,
    simulated: bool,
) -> None:
    """Prints a human-readable summary of one saved attempt to stdout.

    Args:
        request: Request facts as returned by `run_attempt`.
        results: Metric observations as returned by `run_attempt`.
        request_id: The saved request's id.
        db_ref: Database the attempt was saved to (shown without credentials).
        simulated: Whether to mark token counts, costs and rates as simulated.
    """
    note = " (simulated)" if simulated else ""
    print(f"Provider: {request['provider']}")
    print(f"Model: {request['model']}")
    print(f"Workload: {request['workload_id']}")
    print(f"Origin: {request['origin_cloud']} / {request['origin_region']}")
    print(f"Request profile: {request['request_profile_id']}")
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
    if request.get("cached_input_price_per_1m") is not None:
        print(
            "Cached input rate (applied only to provider-reported cached"
            f" tokens): ${request['cached_input_price_per_1m']:.2f} per 1M"
            " tokens"
        )
    print(
        f"Saved attempt {request_id} with {len(results)} observations "
        f"to {_db_display(db_ref)}"
    )
