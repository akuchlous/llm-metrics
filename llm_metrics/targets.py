"""Benchmark targets: the exact provider/model/request settings measured.

A measurement means "this workload, sent to this model under these request
settings". `workloads` owns the first part; this module owns the second. Each
`RequestProfile` names one provider, one model, and every request setting the
adapter deliberately sends beyond the workload itself, under a stable
versioned id stored with every attempt (`requests.request_profile_id`).
Provider adapters build their request bodies from their profile, so the stored
id always describes the request that was actually sent.

Rules every profile follows:

- Versioned identity. A profile id names one exact provider, model, endpoint,
  and settings. If a change could make new measurements not directly
  comparable with old ones (a different model, endpoint, reasoning/thinking
  setting, cache control, or any other material setting), add a new version
  and leave the old definition untouched. `tests/test_targets.py` pins every
  profile to catch accidental edits.
- Only what we control. `settings` lists the request fields this benchmark
  sends on purpose. Anything not listed is not sent and is whatever the
  provider defaults to; it is described as such, never given an assumed
  value.
- No invented equivalence. Reasoning/thinking and cache controls differ
  between providers; each profile describes its own provider's control in that
  provider's terms. `reasoning` and `cache_policy` are comparable labels only
  where the providers define them the same way; see `DECISIONS.md` (D062).
- Separate from the workload. A profile never changes workload content or the
  output cap; it only says how the workload's prompt and cap are carried.

`BENCHMARK_TARGETS` holds exactly one real target per provider: the four
targets of the initial cross-provider benchmark. They are deliberate choices
for that experiment (see `DECISIONS.md`), not a model catalogue.

This module imports nothing from llm_metrics, so every other layer can depend
on it.
"""

import dataclasses
import json
import re

# provider.model.vN: lowercase names of letters, digits, hyphens and dots.
_PROFILE_ID = re.compile(r"[a-z0-9-]+\.[a-z0-9.-]+\.v[1-9][0-9]*")


class UnknownTargetError(ValueError):
    """Raised for a provider with no benchmark target (input never echoed)."""


@dataclasses.dataclass(frozen=True)
class RequestProfile:
    """One provider/model and the exact request settings sent to it.

    Attributes:
        profile_id: Stable versioned id, e.g. "anthropic.claude-haiku-5-5.v1".
            Stored with every attempt; never reused for different settings.
        provider: Provider name, as stored in `requests.provider`.
        model: Exact model id sent to the provider (`requests.model`).
        endpoint: HTTP method, URL and protocol the adapter uses.
        output_cap_field: The request field that carries the workload's
            `max_output_tokens` (dotted path for nested fields).
        settings: (dotted field path, JSON value text) for every request
            field sent on purpose besides the model, the prompt, the output
            cap, and the streaming flag. JSON text keeps the profile
            immutable and makes the sent value exact.
        reasoning: The effective reasoning/thinking condition, in the
            provider's own terms.
        cache_policy: A value of `providers.CACHE_POLICIES` (never "unknown"):
            what the request asks of the provider's prompt cache.
        api_key_variable: Environment variable holding the provider API key;
            None for the simulated provider.
    """

    profile_id: str
    provider: str
    model: str
    endpoint: str
    output_cap_field: str
    settings: tuple[tuple[str, str], ...]
    reasoning: str
    cache_policy: str
    api_key_variable: str | None

    def __post_init__(self):
        """Validates the identity and that every setting is valid JSON.

        Raises:
            ValueError: If the id does not match `provider.model.vN` for this
                profile's provider and model, or a setting is not JSON.
        """
        if not _PROFILE_ID.fullmatch(self.profile_id) or not (
            self.profile_id.startswith(f"{self.provider}.{self.model}.v")
        ):
            raise ValueError(f"Invalid profile id {self.profile_id!r}.")
        for _, value in self.settings:
            json.loads(value)

    def apply_settings(self, body: dict) -> dict:
        """Returns `body` with every profile setting added at its path.

        Nested paths ("generation_config.thinking_level") are merged into
        existing objects, so a setting never replaces fields the adapter has
        already placed there (such as the output cap).
        """
        for path, value in self.settings:
            *parents, leaf = path.split(".")
            target = body
            for name in parents:
                target = target.setdefault(name, {})
            target[leaf] = json.loads(value)
        return body


# The simulated provider of tests and ./run.sh: no network, no settings.
SIMULATED = RequestProfile(
    profile_id="dummy.dummy-model-v1.v1",
    provider="dummy",
    model="dummy-model-v1",
    endpoint="simulated in-process stream (no network)",
    output_cap_field="max_output_tokens",
    settings=(),
    reasoning="not applicable (simulated provider)",
    cache_policy="provider_default",
    api_key_variable=None,
)

# Sources for every fact below, checked 2026-11-01, are in DECISIONS.md (D062)
# and prompts/016-output.md.
OPENAI = RequestProfile(
    profile_id="openai.gpt-6-luna.v1",
    provider="openai",
    model="gpt-6-luna",
    endpoint="POST https://api.openai.com/v1/responses (streaming SSE)",
    output_cap_field="max_output_tokens",
    settings=(
        # Do not keep the response on OpenAI's side.
        ("store", "false"),
        # The model's default effort is "medium"; "none" measures plain
        # generation without reasoning.
        ("reasoning.effort", '"none"'),
        # Explicit cache mode with no breakpoints: no prompt caching or cache
        # writes, per OpenAI's prompt caching guide.
        ("prompt_cache_options.mode", '"explicit"'),
    ),
    reasoning="reasoning.effort=none (reasoning off)",
    cache_policy="disabled",
    api_key_variable="OPENAI_API_KEY",
)
ANTHROPIC = RequestProfile(
    profile_id="anthropic.claude-haiku-5-5.v1",
    provider="anthropic",
    model="claude-haiku-5-5",
    endpoint=(
        "POST https://api.anthropic.com/v1/messages"
        " (anthropic-version 2023-06-01, streaming SSE)"
    ),
    output_cap_field="max_tokens",
    settings=(
        # Adaptive thinking is on by default for this model; "disabled" is
        # accepted at the default effort ("medium"). Effort is not sent.
        ("thinking.type", '"disabled"'),
    ),
    reasoning=(
        "thinking.type=disabled (thinking off); output_config.effort not"
        " sent (provider default)"
    ),
    # The Messages API caches only at cache_control breakpoints; none is
    # sent, but that is the provider's default behavior, not a control.
    cache_policy="provider_default",
    api_key_variable="ANTHROPIC_API_KEY",
)
GOOGLE = RequestProfile(
    profile_id="google.gemini-3.5-flash-lite.v1",
    provider="google",
    model="gemini-3.5-flash-lite",
    endpoint=(
        "POST https://generativelanguage.googleapis.com/v1beta/interactions"
        "?alt=sse (Interactions API, streaming SSE)"
    ),
    output_cap_field="generation_config.max_output_tokens",
    settings=(
        # Do not keep the interaction on Google's side (stored by default).
        ("store", "false"),
        # The lowest level the model offers (also its default), pinned so a
        # default change cannot silently alter the measurement. It does not
        # turn thinking fully off.
        ("generation_config.thinking_level", '"minimal"'),
    ),
    reasoning=(
        "thinking_level=minimal (lowest offered; thinking cannot be turned"
        " fully off)"
    ),
    # Implicit caching is on by default; no per-request control documented.
    cache_policy="provider_default",
    api_key_variable="GEMINI_API_KEY",
)
XAI = RequestProfile(
    profile_id="xai.grok-4.20-0309-non-reasoning.v1",
    provider="xai",
    model="grok-4.20-0309-non-reasoning",
    endpoint="POST https://api.x.ai/v1/responses (streaming SSE)",
    output_cap_field="max_output_tokens",
    settings=(
        # Do not keep the response on xAI's side (stored 30 days otherwise).
        ("store", "false"),
    ),
    # The non-reasoning variant: no reasoning field exists to send.
    reasoning="non-reasoning model variant; no reasoning field sent",
    # Prompt caching is automatic; no documented way to disable it.
    cache_policy="provider_default",
    api_key_variable="XAI_API_KEY",
)

BENCHMARK_TARGETS = (OPENAI, ANTHROPIC, GOOGLE, XAI)
_PROFILES = {
    profile.profile_id: profile for profile in (SIMULATED, *BENCHMARK_TARGETS)
}
_TARGETS = {profile.provider: profile for profile in BENCHMARK_TARGETS}


def get_profile(profile_id: str) -> RequestProfile | None:
    """Returns the registered profile with this id, or None."""
    return _PROFILES.get(profile_id)


def get_target(provider: str) -> RequestProfile:
    """Returns the benchmark target of a real provider.

    Raises:
        UnknownTargetError: If `provider` has no target. The message lists the
            valid names and never echoes the input.
    """
    try:
        return _TARGETS[provider]
    except KeyError:
        raise UnknownTargetError(
            "Unknown provider. Valid providers: " + ", ".join(_TARGETS)
        ) from None
