"""Provider abstraction and a simulated provider for testing."""

import math
import time
from collections.abc import Iterator
from dataclasses import dataclass

from llm_metrics.outcomes import FAILURE_CATEGORIES

# What a benchmark request asked of the provider's prompt/prefix cache. A
# requested policy, not a claim about every internal provider cache:
#   disabled          the request used a documented provider control that
#                     establishes no cache reuse
#   enabled           the request explicitly allowed/requested cache reuse
#   provider_default  no cache control was sent; the provider decides
#   unknown           cannot be established (attempts before Step 013)
CACHE_POLICIES = ("disabled", "enabled", "provider_default", "unknown")


@dataclass(frozen=True)
class Usage:
    """Token counts the provider attributes to one request.

    Sent once, as the last item of the stream (as real APIs report usage in a
    final event). Counts are in the provider's own token units.
    `provider_request_id` is the provider's own identifier for the request
    (e.g. OpenAI's x-request-id), if it gave one: diagnostic metadata stored
    beside llm-metrics' own request id, never a replacement for it.
    `cached_input_tokens` is the provider-reported part of input_tokens read
    from its prompt cache: 0 when the provider reported zero, None when it did
    not report it. Never inferred.
    """

    input_tokens: int
    output_tokens: int
    provider_request_id: str | None = None
    cached_input_tokens: int | None = None


class ProviderFailure(Exception):
    """Raised by a provider when an attempt fails, with a stable internal category
    (a key of outcomes.FAILURE_CATEGORIES). Adapters map their native errors
    (HTTP status codes, SDK exceptions) to a category here; the message is for
    humans and is never stored. `diagnostics` holds sanitized identifiers (e.g.
    HTTP status, provider error code, request id) that may be printed for local
    debugging; it is never stored. `provider_request_id` (as in Usage) is stored
    with the failed attempt when known."""

    def __init__(self, category: str, message: str = "", diagnostics: dict | None = None,
                 provider_request_id: str | None = None):
        if category not in FAILURE_CATEGORIES:
            raise ValueError(f"Unknown failure category {category!r}.")
        super().__init__(message or category)
        self.category = category
        # Sanitized, non-secret identifiers for local debugging only (never stored).
        self.diagnostics = diagnostics or {}
        self.provider_request_id = provider_request_id


class LLMProvider:
    """Base class for anything that streams a response to a prompt.

    `stream()` yields text chunks (str) followed by exactly one `Usage`. Chunks
    are not tokens: a chunk may hold zero, one, or several provider tokens.
    The provider must not generate more than `max_output_tokens` output tokens.
    On failure it raises ProviderFailure (possibly after some chunks).
    `cache_policy` (one of CACHE_POLICIES) is what every request this provider
    sends asks of the provider's cache; it is stored with each attempt.
    """

    name: str
    model: str
    cache_policy: str = "provider_default"

    def stream(self, prompt: str, max_output_tokens: int) -> Iterator[str | Usage]:
        raise NotImplementedError


def simulated_token_count(text: str) -> int:
    """SIMULATED tokenizer for the dummy provider: one token per 4 characters,
    rounded up. Deterministic for tests; it does not match any real provider's
    tokenizer or billing."""
    return math.ceil(len(text) / 4)


class DummyProvider(LLMProvider):
    """Simulated streaming provider. Never calls a network service.

    Waits `first_token_delay_s` seconds, then yields `tokens` (text chunks) one
    by one, waiting `inter_token_delay_s` seconds before each chunk after the
    first. Stops before a chunk that would take the output past
    `max_output_tokens`. Finally yields `Usage` counted with
    `simulated_token_count` (input: the prompt; output: all text yielded).

    Deterministic simulated failures, for tests (no randomness, no extra sleep):
    `fail_with=<category>` raises ProviderFailure(category) after
    `fail_after_chunks` chunks; `omit_usage=True` ends the stream without Usage.
    """

    name = "dummy"
    model = "dummy-model-v1"

    def __init__(
        self,
        first_token_delay_s: float = 0.1,
        tokens: tuple[str, ...] = ("This", " is", " a", " dummy", " response."),
        inter_token_delay_s: float = 0.02,
        fail_with: str | None = None,
        fail_after_chunks: int = 0,
        omit_usage: bool = False,
    ):
        if fail_with is not None and fail_with not in FAILURE_CATEGORIES:
            raise ValueError(f"Unknown failure category {fail_with!r}.")
        self.first_token_delay_s = first_token_delay_s
        self.tokens = tokens
        self.inter_token_delay_s = inter_token_delay_s
        self.fail_with = fail_with
        self.fail_after_chunks = fail_after_chunks
        self.omit_usage = omit_usage

    def stream(self, prompt: str, max_output_tokens: int) -> Iterator[str | Usage]:
        if max_output_tokens < 1:
            raise ValueError("max_output_tokens must be at least 1.")
        time.sleep(self.first_token_delay_s)
        output = ""
        for i, chunk in enumerate(self.tokens):
            if self.fail_with is not None and i == self.fail_after_chunks:
                raise ProviderFailure(self.fail_with, "simulated failure")
            if simulated_token_count(output + chunk) > max_output_tokens:
                break
            if i > 0:
                time.sleep(self.inter_token_delay_s)
            output += chunk
            yield chunk
        if self.fail_with is not None:  # fail_after_chunks >= chunks streamed
            raise ProviderFailure(self.fail_with, "simulated failure")
        if self.omit_usage:
            return
        yield Usage(
            input_tokens=simulated_token_count(prompt),
            output_tokens=simulated_token_count(output),
        )
