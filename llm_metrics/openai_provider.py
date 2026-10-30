"""OpenAI provider: one streamed Responses API call, standard library only.

POST https://api.openai.com/v1/responses with `stream: true`. The server-sent
event stream is translated into the LLMProvider contract:

- `response.output_text.delta` -> its text, as one chunk
- `response.completed`         -> Usage(input_tokens, output_tokens) from the
                                  response's authoritative `usage` (last item)
- `response.incomplete` because `max_output_tokens` was reached -> Usage too:
                                  the cap was hit, the output is still valid
- other event types are ignored

Failures are mapped here, at the provider boundary, to the stable categories
of outcomes.py by raising ProviderFailure (never with response bodies, prompts,
or the API key in the message). Errors that mean our own request or
configuration is wrong (authentication, permission, bad request, unknown model)
are not provider failures: they raise RequestRejected and are not recorded.

There is no retry: one stream() call is exactly one HTTP request.
"""

import http.client
import json
import socket
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator

from llm_metrics.providers import LLMProvider, ProviderFailure, Usage

API_URL = "https://api.openai.com/v1/responses"
TIMEOUT_S = 60  # connect and per-read socket timeout


class RequestRejected(Exception):
    """OpenAI rejected the request itself (HTTP 400/401/403/404/...): our API key,
    permissions, model name, or parameters are wrong. Not a benchmark outcome."""

    def __init__(self, status: int):
        super().__init__(f"OpenAI rejected the request (HTTP {status}).")
        self.status = status


def _failure_for_status(status: int) -> ProviderFailure | RequestRejected:
    if status == 429:
        return ProviderFailure("rate_limited", "HTTP 429")
    if status in (408, 504):
        return ProviderFailure("timeout", f"HTTP {status}")
    if status >= 500:
        return ProviderFailure("provider_error", f"HTTP {status}")
    return RequestRejected(status)


def _usage(response: dict) -> Usage:
    """Authoritative token counts from a final response object, or invalid_response."""
    usage = response.get("usage") if isinstance(response, dict) else None
    try:
        input_tokens = usage["input_tokens"]
        output_tokens = usage["output_tokens"]
    except (KeyError, TypeError):
        raise ProviderFailure("invalid_response", "final event without usage") from None
    for count in (input_tokens, output_tokens):
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ProviderFailure("invalid_response", "usage counts are not non-negative integers")
    return Usage(input_tokens=input_tokens, output_tokens=output_tokens)


def _events(lines: Iterator[bytes]) -> Iterator[dict]:
    """Parse server-sent events (one JSON object per event, in `data:` lines)."""
    data: list[str] = []
    for raw in lines:
        line = raw.decode("utf-8").rstrip("\r\n")
        if line.startswith("data:"):
            data.append(line[5:].lstrip())
        elif line == "" and data:
            payload = "\n".join(data)
            data = []
            if payload == "[DONE]":
                return
            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                raise ProviderFailure("invalid_response", "event is not JSON") from None
            if not isinstance(event, dict):
                raise ProviderFailure("invalid_response", "event is not an object")
            yield event
        # other SSE fields ("event:", "id:", comments) carry nothing we need


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-6-luna",
        opener: Callable = urllib.request.urlopen,
    ):
        if not api_key:
            raise ValueError("An OpenAI API key is required.")
        self.model = model
        self._api_key = api_key
        self._open = opener  # injectable so tests never touch the network

    def __repr__(self) -> str:  # never show the key
        return f"OpenAIProvider(model={self.model!r})"

    def _request(self, prompt: str, max_output_tokens: int) -> urllib.request.Request:
        body = {
            "model": self.model,
            "input": prompt,
            "max_output_tokens": max_output_tokens,
            "stream": True,
            "store": False,  # do not keep the response on OpenAI's side
        }
        return urllib.request.Request(
            API_URL,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
        )

    def stream(self, prompt: str, max_output_tokens: int) -> Iterator[str | Usage]:
        if max_output_tokens < 1:
            raise ValueError("max_output_tokens must be at least 1.")
        try:
            response = self._open(self._request(prompt, max_output_tokens), timeout=TIMEOUT_S)
        except urllib.error.HTTPError as e:
            raise _failure_for_status(e.code) from None
        except (TimeoutError, socket.timeout):
            raise ProviderFailure("timeout", "connection timed out") from None
        except (urllib.error.URLError, http.client.HTTPException, ConnectionError, OSError):
            raise ProviderFailure("transport_error", "could not connect") from None

        with response:
            try:
                for event in _events(iter(response.readline, b"")):
                    kind = event.get("type")
                    if kind == "response.output_text.delta":
                        delta = event.get("delta")
                        if not isinstance(delta, str):
                            raise ProviderFailure("invalid_response", "delta is not text")
                        yield delta
                    elif kind == "response.completed":
                        yield _usage(event.get("response"))
                        return
                    elif kind == "response.incomplete":
                        final = event.get("response") or {}
                        reason = (final.get("incomplete_details") or {}).get("reason")
                        if reason != "max_output_tokens":
                            raise ProviderFailure("provider_error", "response incomplete")
                        yield _usage(final)
                        return
                    elif kind == "response.failed":
                        raise ProviderFailure("provider_error", "response failed")
                    elif kind == "error":
                        code = str(event.get("code") or "")
                        category = "rate_limited" if "rate_limit" in code else "provider_error"
                        raise ProviderFailure(category, "error event")
            except (TimeoutError, socket.timeout):
                raise ProviderFailure("timeout", "stream read timed out") from None
            except (http.client.HTTPException, ConnectionError, OSError):
                raise ProviderFailure("transport_error", "stream interrupted") from None
            except UnicodeDecodeError:
                raise ProviderFailure("invalid_response", "stream is not UTF-8") from None
        # Stream ended without a final event: measurement reports missing usage
        # as invalid_response.
