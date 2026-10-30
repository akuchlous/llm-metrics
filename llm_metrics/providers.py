"""Provider abstraction and a simulated provider for testing."""

import math
import time
from collections.abc import Iterator
from dataclasses import dataclass


@dataclass(frozen=True)
class Usage:
    """Token counts the provider attributes to one request.

    Sent once, as the last item of the stream (as real APIs report usage in a
    final event). Counts are in the provider's own token units.
    """

    input_tokens: int
    output_tokens: int


class LLMProvider:
    """Base class for anything that streams a response to a prompt.

    `stream()` yields text chunks (str) followed by exactly one `Usage`. Chunks
    are not tokens: a chunk may hold zero, one, or several provider tokens.
    The provider must not generate more than `max_output_tokens` output tokens.
    """

    name: str
    model: str

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
    """

    name = "dummy"
    model = "dummy-model-v1"

    def __init__(
        self,
        first_token_delay_s: float = 0.1,
        tokens: tuple[str, ...] = ("This", " is", " a", " dummy", " response."),
        inter_token_delay_s: float = 0.02,
    ):
        self.first_token_delay_s = first_token_delay_s
        self.tokens = tokens
        self.inter_token_delay_s = inter_token_delay_s

    def stream(self, prompt: str, max_output_tokens: int) -> Iterator[str | Usage]:
        if max_output_tokens < 1:
            raise ValueError("max_output_tokens must be at least 1.")
        time.sleep(self.first_token_delay_s)
        output = ""
        for i, chunk in enumerate(self.tokens):
            if simulated_token_count(output + chunk) > max_output_tokens:
                break
            if i > 0:
                time.sleep(self.inter_token_delay_s)
            output += chunk
            yield chunk
        yield Usage(
            input_tokens=simulated_token_count(prompt),
            output_tokens=simulated_token_count(output),
        )
