"""Provider abstraction and a simulated provider for testing."""

import time
from collections.abc import Iterator


class LLMProvider:
    """Base class for anything that streams tokens in response to a prompt."""

    name: str
    model: str

    def stream(self, prompt: str) -> Iterator[str]:
        raise NotImplementedError


class DummyProvider(LLMProvider):
    """Simulated streaming provider. Never calls a network service.

    Waits `first_token_delay_s` seconds, then yields `tokens` one by one,
    waiting `inter_token_delay_s` seconds before each token after the first.
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

    def stream(self, prompt: str) -> Iterator[str]:
        time.sleep(self.first_token_delay_s)
        for i, token in enumerate(self.tokens):
            if i > 0:
                time.sleep(self.inter_token_delay_s)
            yield token
