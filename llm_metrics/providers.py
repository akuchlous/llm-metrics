"""Provider contract shared by all LLM providers, and the simulated provider.

A provider turns one prompt into one streamed response. The contract here is
the boundary between provider adapters (which know HTTP, SDKs, and native error
formats) and measurement (which knows only text chunks, a final `Usage`, and
`ProviderFailure`). Adapters translate everything provider-specific at this
boundary; nothing downstream depends on a provider's wire format.
"""

from collections.abc import Iterator
import dataclasses
import math
import time

from llm_metrics import outcomes

# What a benchmark request asks of the provider's prompt/prefix cache. This is
# the requested policy, not a claim about every internal provider cache:
#   disabled          A documented provider control establishing no cache
#                     reuse was sent with the request.
#   enabled           Cache reuse was explicitly allowed or requested.
#   provider_default  No cache control was sent; the provider decides.
#   unknown           Cannot be established (attempts recorded before cache
#                     policy was tracked). Never used for new attempts.
# The values are stored in the database, so they must never be renamed.
CACHE_POLICIES = ("disabled", "enabled", "provider_default", "unknown")


@dataclasses.dataclass(frozen=True)
class Usage:
    """What the provider reports about one completed request.

    Yielded exactly once, as the last item of a successful stream, mirroring
    real APIs that report usage in a final event. Token counts are in the
    provider's own token units and are the only source of token facts:
    measurement never derives tokens from chunk counts.

    Attributes:
        input_tokens: Provider-reported input tokens.
        output_tokens: Provider-reported output tokens.
        provider_request_id: The provider's own id for the request (e.g.
            OpenAI's `x-request-id`), or None. Diagnostic metadata stored beside
            llm-metrics' own request id, never a replacement for it.
        cached_input_tokens: The part of `input_tokens` the provider reports it
            read from its prompt cache. 0 means the provider reported zero;
            None means it did not report the value. Never inferred.
    """

    input_tokens: int
    output_tokens: int
    provider_request_id: str | None = None
    cached_input_tokens: int | None = None


class ProviderFailure(Exception):
    """Raised by a provider when an attempt fails.

    Adapters map native errors (HTTP statuses, SDK exceptions, error events) to
    one stable category here, so stored outcomes never depend on provider
    wording. The exception message is for humans and is never stored.

    Attributes:
        category: A key of `outcomes.FAILURE_CATEGORIES`.
        diagnostics: Sanitized identifiers (code path, HTTP status, provider
            error code, request id) for local debugging only. Never stored, and
            never containing secrets, prompts, response text, or raw bodies.
        provider_request_id: As in `Usage`; stored with the failed attempt when
            known.
    """

    def __init__(
        self,
        category: str,
        message: str = "",
        diagnostics: dict[str, str] | None = None,
        provider_request_id: str | None = None,
    ):
        """Initializes the failure.

        Raises:
            ValueError: If `category` is not a known failure category, so a
                typo can never create a new outcome in stored data.
        """
        if category not in outcomes.FAILURE_CATEGORIES:
            raise ValueError(f"Unknown failure category {category!r}.")
        super().__init__(message or category)
        self.category = category
        self.diagnostics = diagnostics or {}
        self.provider_request_id = provider_request_id


class LLMProvider:
    """Base class for anything that streams a response to a prompt.

    Attributes:
        name: Provider name, e.g. "openai". Stored with every attempt.
        model: Model name, e.g. "gpt-6-luna". Stored with every attempt.
        cache_policy: One of `CACHE_POLICIES` (never "unknown"): what every
            request this provider sends asks of the provider's prompt cache.
            Declared by the provider so the stored value cannot drift from the
            request actually sent.
    """

    name: str
    model: str
    cache_policy: str = "provider_default"

    def stream(
        self, prompt: str, max_output_tokens: int
    ) -> Iterator[str | Usage]:
        """Streams the response to `prompt` as one provider call.

        Chunks are not tokens: a chunk may hold zero, one, or several provider
        tokens. Implementations must not request more than `max_output_tokens`
        output tokens and must not retry, so one call is one attempt.

        Args:
            prompt: Text to send. Never logged or stored.
            max_output_tokens: Output token cap requested from the provider.

        Yields:
            Text chunks (str), then exactly one `Usage`.

        Raises:
            ProviderFailure: When the attempt fails, possibly after some chunks.
        """
        raise NotImplementedError


def simulated_token_count(text: str) -> int:
    """Counts tokens with the SIMULATED tokenizer of the dummy provider.

    One token per 4 characters, rounded up: deterministic for tests, and not
    matching any real provider's tokenizer or billing.
    """
    return math.ceil(len(text) / 4)


class DummyProvider(LLMProvider):
    """Simulated streaming provider for tests and `./run.sh`. No network access.

    Waits `first_token_delay_s`, then yields `tokens` one by one, waiting
    `inter_token_delay_s` before each chunk after the first. Stops before a
    chunk that would take the output past `max_output_tokens`, then yields a
    `Usage` counted with `simulated_token_count` (input: the prompt; output:
    all text yielded). It sends no cache control and reports no cached tokens.

    Failures are deterministic, for tests (no randomness, no extra sleep):
    `fail_with` raises `ProviderFailure(fail_with)` before chunk index
    `fail_after_chunks` (or after the last chunk if that index is past the
    end), and `omit_usage` ends the stream without a `Usage`.
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
        """Initializes the simulated provider.

        Raises:
            ValueError: If `fail_with` is not a known failure category.
        """
        if (
            fail_with is not None
            and fail_with not in outcomes.FAILURE_CATEGORIES
        ):
            raise ValueError(f"Unknown failure category {fail_with!r}.")
        self.first_token_delay_s = first_token_delay_s
        self.tokens = tokens
        self.inter_token_delay_s = inter_token_delay_s
        self.fail_with = fail_with
        self.fail_after_chunks = fail_after_chunks
        self.omit_usage = omit_usage

    def stream(
        self, prompt: str, max_output_tokens: int
    ) -> Iterator[str | Usage]:
        """See `LLMProvider.stream`.

        Raises:
            ValueError: If `max_output_tokens` is less than 1.
            ProviderFailure: When configured with `fail_with`.
        """
        if max_output_tokens < 1:
            raise ValueError("max_output_tokens must be at least 1.")
        time.sleep(self.first_token_delay_s)
        output = ""
        for index, chunk in enumerate(self.tokens):
            if self.fail_with is not None and index == self.fail_after_chunks:
                raise ProviderFailure(self.fail_with, "simulated failure")
            if simulated_token_count(output + chunk) > max_output_tokens:
                break
            if index > 0:
                time.sleep(self.inter_token_delay_s)
            output += chunk
            yield chunk
        if self.fail_with is not None:
            # fail_after_chunks was at or past the number of chunks streamed.
            raise ProviderFailure(self.fail_with, "simulated failure")
        if self.omit_usage:
            return
        yield Usage(
            input_tokens=simulated_token_count(prompt),
            output_tokens=simulated_token_count(output),
        )
