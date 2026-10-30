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

Every failure carries `diagnostics`: sanitized identifiers only (which code
path failed, HTTP status, the `x-request-id` header, and OpenAI's error
code/type/param and incomplete reason), each restricted to a short
[A-Za-z0-9_.:-] token or replaced by "<redacted>". Never messages, bodies,
headers, prompts, response text, or the API key. They are for local debugging
(`real_smoke --debug`) and are never stored.

There is no retry: one stream() call is exactly one HTTP request.
"""

import http.client
import json
import re
import socket
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator

from llm_metrics.providers import LLMProvider, ProviderFailure, Usage

API_URL = "https://api.openai.com/v1/responses"
TIMEOUT_S = 60  # connect and per-read socket timeout
# Reasoning tokens are billed as output and count against max_output_tokens;
# "none" keeps the 64-token benchmark answer visible and its cost controlled.
# Supported for gpt-6-luna per third-party docs citing OpenAI (official page
# unreachable from the implementation environment). If the API rejects it,
# the request fails with HTTP 400 (RequestRejected, not recorded) and
# `--debug` shows error_param.
REASONING_EFFORT = "none"
_ERROR_BODY_LIMIT = 64 * 1024  # bytes read from an HTTP error body to find its code
_SAFE_TOKEN = re.compile(r"[A-Za-z0-9_.:-]{1,100}")


def _safe(value) -> str:
    """A short identifier-like token, or "<redacted>". Never free text."""
    if isinstance(value, bool) or value is None:
        return "<redacted>" if value is not None else "<none>"
    text = str(value)
    return text if _SAFE_TOKEN.fullmatch(text) else "<redacted>"


def _error_fields(error) -> dict:
    """Sanitized code/type/param of an OpenAI error object (dict); nothing else."""
    if not isinstance(error, dict):
        return {}
    return {f"error_{k}": _safe(error[k]) for k in ("code", "type", "param") if k in error}


class RequestRejected(Exception):
    """OpenAI rejected the request itself (HTTP 400/401/403/404/...): our API key,
    permissions, model name, or parameters are wrong. Not a benchmark outcome."""

    def __init__(self, status: int, diagnostics: dict | None = None):
        super().__init__(f"OpenAI rejected the request (HTTP {status}).")
        self.status = status
        self.diagnostics = diagnostics or {}


def _http_error_diagnostics(error: urllib.error.HTTPError) -> dict:
    """Sanitized status, request id, and error code/type/param of an HTTP error.
    The body is read (bounded) only to extract those fields and is discarded."""
    diagnostics = {"where": "http_status", "http_status": _safe(error.code)}
    request_id = error.headers.get("x-request-id") if error.headers else None
    if request_id is not None:
        diagnostics["request_id"] = _safe(request_id)
    try:
        body = json.loads(error.read(_ERROR_BODY_LIMIT) or b"{}")
    except (ValueError, OSError):
        body = None
    if isinstance(body, dict):
        diagnostics.update(_error_fields(body.get("error")))
    return diagnostics


def _failure_for_status(error: urllib.error.HTTPError) -> ProviderFailure | RequestRejected:
    status = error.code
    diagnostics = _http_error_diagnostics(error)
    if status == 429:
        return ProviderFailure("rate_limited", "HTTP 429", diagnostics)
    if status in (408, 504):
        return ProviderFailure("timeout", f"HTTP {status}", diagnostics)
    if status >= 500:
        return ProviderFailure("provider_error", f"HTTP {status}", diagnostics)
    return RequestRejected(status, diagnostics)


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
            "reasoning": {"effort": REASONING_EFFORT},
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
            raise _failure_for_status(e) from None
        except (TimeoutError, socket.timeout):
            raise ProviderFailure("timeout", "connection timed out", {"where": "open"}) from None
        except (urllib.error.URLError, http.client.HTTPException, ConnectionError, OSError) as e:
            raise ProviderFailure("transport_error", "could not connect",
                                  {"where": "open", "exception": type(e).__name__}) from None

        headers = getattr(response, "headers", None)
        request_id = headers.get("x-request-id") if headers else None
        stream_info = {"http_status": _safe(getattr(response, "status", None))}
        if request_id is not None:
            stream_info["request_id"] = _safe(request_id)

        def failure(category: str, where: str, **extra) -> ProviderFailure:
            return ProviderFailure(category, where, {"where": where, **stream_info, **extra})

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
                            raise failure("provider_error", "event:response.incomplete",
                                          incomplete_reason=_safe(reason))
                        yield _usage(final)
                        return
                    elif kind == "response.failed":
                        final = event.get("response") or {}
                        raise failure("provider_error", "event:response.failed",
                                      response_status=_safe(final.get("status")),
                                      **_error_fields(final.get("error")))
                    elif kind == "error":
                        # Details may be nested ({"type": "error", "error": {...}})
                        # or top-level; the event's own "type" is always "error".
                        nested = event.get("error")
                        details = nested if isinstance(nested, dict) else {
                            k: v for k, v in event.items() if k != "type"}
                        code = str(details.get("code") or "")
                        category = "rate_limited" if "rate_limit" in code else "provider_error"
                        raise failure(category, "event:error", **_error_fields(details))
            except ProviderFailure as e:
                if not e.diagnostics:  # e.g. invalid_response from _events/_usage
                    e.diagnostics = {"where": "stream", **stream_info}
                raise
            except (TimeoutError, socket.timeout):
                raise failure("timeout", "stream_read") from None
            except (http.client.HTTPException, ConnectionError, OSError) as e:
                raise failure("transport_error", "stream_read", exception=type(e).__name__) from None
            except UnicodeDecodeError:
                raise failure("invalid_response", "stream_decode") from None
        # Stream ended without a final event: measurement reports missing usage
        # as invalid_response.
