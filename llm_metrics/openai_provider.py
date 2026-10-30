"""OpenAI provider: one streamed Responses API call, standard library only.

Sends `POST https://api.openai.com/v1/responses` with `stream: true` and
translates the server-sent event stream into the `LLMProvider` contract:

- `response.output_text.delta`: its text, as one chunk.
- `response.completed`: the final `Usage` from the response's authoritative
  `usage` (input/output tokens, and cached input tokens from
  `usage.input_tokens_details.cached_tokens` when reported).
- `response.incomplete` because `max_output_tokens` was reached: also a final
  `Usage`, because hitting the requested cap still yields a valid response.
- Other event types carry nothing we need and are ignored.

Error mapping happens here, at the provider boundary:

- Provider-side failures raise `ProviderFailure` with a stable category from
  `outcomes`, and are recorded as failed attempts.
- Errors that mean our own request, configuration, or account is wrong
  (authentication, permission, bad parameters, unknown model, no credit) raise
  `RequestRejected` and are not recorded, because they say nothing about the
  provider's reliability. Account-credit errors are recognized whether they
  arrive as an HTTP 429 or as an error event inside an HTTP 200 stream.

Privacy: no exception message, diagnostic, or stored value ever contains the
API key, the prompt, response text, headers, or raw error bodies. Diagnostics
are short sanitized identifiers for `real_smoke --debug` and are never stored.

There is no retry: one `stream()` call is exactly one HTTP request (the SDK is
not used partly because it retries by default).
"""

from collections.abc import Callable, Iterator
import http.client
import json
import re
import socket
import urllib.error
import urllib.request

from llm_metrics import providers

API_URL = "https://api.openai.com/v1/responses"
TIMEOUT_S = 60  # Connect and per-read socket timeout, not a total deadline.
# Set explicitly so the benchmark measures plain text generation rather than
# the model's default reasoning effort ("medium"). Reasoning tokens are billed
# as output and count against max_output_tokens. Official model page
# (https://developers.openai.com/api/docs/models/gpt-6-luna, checked
# 2026-10-30): "`reasoning.effort` supports `none`, `low`, `medium` (default),
# `high`, `xhigh`, and `max`."
REASONING_EFFORT = "none"
# Explicit cache mode with no breakpoints disables prompt caching. Official
# prompt caching guide (https://developers.openai.com/api/docs/guides/
# prompt-caching, "GPT-5.6 and later", checked 2026-10-30): "When no explicit
# breakpoints are placed, the request does not use prompt caching or create
# cache writes." Recorded as cache_policy "disabled". If the model rejected
# the field, the request would fail with HTTP 400 (RequestRejected, not
# recorded; `--debug` shows error_param).
PROMPT_CACHE_OPTIONS = {"mode": "explicit"}
# An HTTP error body is read only to find its error code, so cap the read.
_ERROR_BODY_LIMIT = 64 * 1024
# Diagnostics and stored ids are restricted to short identifier-like tokens,
# so free text (messages, prompts, secrets) can never leak through them.
_SAFE_TOKEN = re.compile(r"[A-Za-z0-9_.:-]{1,100}")
# Error codes/types meaning our account cannot pay, not that OpenAI failed.
_ACCOUNT_ERRORS = frozenset({"insufficient_quota", "credit_balance_exhausted"})


def _safe(value) -> str:
    """Returns `value` if it is a short identifier-like token.

    Returns "<none>" for None and "<redacted>" for anything else (free text,
    booleans, long values), so diagnostics never carry provider wording.
    """
    if isinstance(value, bool) or value is None:
        return "<redacted>" if value is not None else "<none>"
    text = str(value)
    return text if _SAFE_TOKEN.fullmatch(text) else "<redacted>"


def _error_fields(error) -> dict[str, str]:
    """Returns the sanitized code/type/param of an OpenAI error object.

    The message is deliberately dropped. Returns {} if `error` is not a dict.
    """
    if not isinstance(error, dict):
        return {}
    return {
        f"error_{key}": _safe(error[key])
        for key in ("code", "type", "param")
        if key in error
    }


def _provider_request_id(headers) -> str | None:
    """Returns OpenAI's `x-request-id` header if it is a safe token.

    Returns None otherwise, never "<redacted>": a redaction marker is not an id
    and must not be stored as one.
    """
    value = headers.get("x-request-id") if headers else None
    if isinstance(value, str) and _SAFE_TOKEN.fullmatch(value):
        return value
    return None


def _is_account_error(error) -> bool:
    return isinstance(error, dict) and any(
        error.get(key) in _ACCOUNT_ERRORS for key in ("code", "type")
    )


def _error_event_details(event: dict) -> dict:
    """Returns the error object of a stream `error` event.

    The API documents the fields at the top level but also sends them nested as
    {"type": "error", "error": {...}}. The event's own "type" is always "error"
    and must never be read as the error's type.
    """
    nested = event.get("error")
    if isinstance(nested, dict):
        return nested
    return {key: value for key, value in event.items() if key != "type"}


def _is_count(value) -> bool:
    """Whether `value` is a non-negative int (booleans excluded)."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


class RequestRejected(Exception):
    """OpenAI rejected the request itself; not a benchmark outcome.

    Raised for HTTP 400/401/403/404 and other non-retryable client errors, and
    for account-credit errors: our key, permissions, model name, parameters, or
    account are wrong. Callers must not record the attempt.

    Attributes:
        status: HTTP status (200 when the rejection arrived inside a stream).
        diagnostics: Sanitized identifiers for `--debug`; never stored.
    """

    def __init__(self, status: int, diagnostics: dict[str, str] | None = None):
        super().__init__(f"OpenAI rejected the request (HTTP {status}).")
        self.status = status
        self.diagnostics = diagnostics or {}


def _http_error_diagnostics(
    error: urllib.error.HTTPError,
) -> tuple[dict[str, str], bool]:
    """Extracts sanitized diagnostics from an HTTP error response.

    The body is read (bounded) only to find the error code/type/param and is
    then discarded.

    Returns:
        (diagnostics, is_account_error).
    """
    diagnostics = {"where": "http_status", "http_status": _safe(error.code)}
    request_id = error.headers.get("x-request-id") if error.headers else None
    if request_id is not None:
        diagnostics["request_id"] = _safe(request_id)
    try:
        body = json.loads(error.read(_ERROR_BODY_LIMIT) or b"{}")
    except (ValueError, OSError):
        body = None
    error_object = body.get("error") if isinstance(body, dict) else None
    diagnostics.update(_error_fields(error_object))
    return diagnostics, _is_account_error(error_object)


def _failure_for_status(
    error: urllib.error.HTTPError,
) -> providers.ProviderFailure | RequestRejected:
    """Maps an HTTP error status to a recorded failure or a rejection."""
    status = error.code
    diagnostics, account_error = _http_error_diagnostics(error)
    if account_error:
        return RequestRejected(status, diagnostics)
    provider_request_id = _provider_request_id(error.headers)
    if status == 429:
        category = "rate_limited"
    elif status in (408, 504):
        category = "timeout"
    elif status >= 500:
        category = "provider_error"
    else:
        return RequestRejected(status, diagnostics)
    return providers.ProviderFailure(
        category, f"HTTP {status}", diagnostics, provider_request_id
    )


def _usage(response: dict, provider_request_id: str | None) -> providers.Usage:
    """Builds the final `Usage` from a final response object.

    Args:
        response: The `response` object of a final event.
        provider_request_id: OpenAI's request id, or None.

    Returns:
        Usage with provider-authoritative token counts. `cached_input_tokens`
        is None when `usage.input_tokens_details.cached_tokens` is absent:
        "not reported" is never turned into 0.

    Raises:
        ProviderFailure: "invalid_response" if usage is missing, a count is not
            a non-negative integer, or cached tokens exceed input tokens.
    """
    usage = response.get("usage") if isinstance(response, dict) else None
    try:
        input_tokens = usage["input_tokens"]
        output_tokens = usage["output_tokens"]
    except (KeyError, TypeError):
        raise providers.ProviderFailure(
            "invalid_response", "final event without usage"
        ) from None
    for count in (input_tokens, output_tokens):
        if not _is_count(count):
            raise providers.ProviderFailure(
                "invalid_response", "usage counts are not non-negative integers"
            )
    details = usage.get("input_tokens_details")
    cached = details.get("cached_tokens") if isinstance(details, dict) else None
    # Cached tokens are a part of input_tokens, so a larger value is malformed.
    if cached is not None and not (
        _is_count(cached) and cached <= input_tokens
    ):
        raise providers.ProviderFailure(
            "invalid_response",
            "cached_tokens is not a count within input_tokens",
        )
    return providers.Usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        provider_request_id=provider_request_id,
        cached_input_tokens=cached,
    )


def _events(lines: Iterator[bytes]) -> Iterator[dict]:
    """Parses server-sent events: one JSON object per event, in `data:` lines.

    Other SSE fields ("event:", "id:", comments) carry nothing we need and are
    skipped. Stops at a `[DONE]` payload.

    Yields:
        Each event as a dict.

    Raises:
        ProviderFailure: "invalid_response" if a payload is not a JSON object.
    """
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
                raise providers.ProviderFailure(
                    "invalid_response", "event is not JSON"
                ) from None
            if not isinstance(event, dict):
                raise providers.ProviderFailure(
                    "invalid_response", "event is not an object"
                )
            yield event


class OpenAIProvider(providers.LLMProvider):
    """Streams one OpenAI Responses API request per `stream()` call.

    Every request sends `PROMPT_CACHE_OPTIONS`, so `cache_policy` is
    "disabled". The API key exists only in the request's Authorization header
    and is never shown by `repr` or stored.
    """

    name = "openai"
    cache_policy = "disabled"

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-6-luna",
        opener: Callable = urllib.request.urlopen,
    ):
        """Initializes the provider.

        Args:
            api_key: OpenAI API key.
            model: Model name to request.
            opener: `urllib.request.urlopen`-compatible callable. Injectable so
                tests never touch the network.

        Raises:
            ValueError: If `api_key` is empty.
        """
        if not api_key:
            raise ValueError("An OpenAI API key is required.")
        self.model = model
        self._api_key = api_key
        self._open = opener

    def __repr__(self) -> str:
        return f"OpenAIProvider(model={self.model!r})"

    def _request(
        self, prompt: str, max_output_tokens: int
    ) -> urllib.request.Request:
        body = {
            "model": self.model,
            "input": prompt,
            "max_output_tokens": max_output_tokens,
            "stream": True,
            "store": False,  # Do not keep the response on OpenAI's side.
            "reasoning": {"effort": REASONING_EFFORT},
            "prompt_cache_options": PROMPT_CACHE_OPTIONS,
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

    def stream(
        self, prompt: str, max_output_tokens: int
    ) -> Iterator[str | providers.Usage]:
        """Sends one request and streams its response.

        See `providers.LLMProvider.stream` for the contract. If the stream ends
        without a final event, no `Usage` is yielded and measurement records
        the attempt as "invalid_response".

        Raises:
            ValueError: If `max_output_tokens` is less than 1.
            ProviderFailure: For provider-side failures, with
                `provider_request_id` set whenever OpenAI sent one.
            RequestRejected: When the request, configuration, or account is at
                fault; the attempt must not be recorded.
        """
        if max_output_tokens < 1:
            raise ValueError("max_output_tokens must be at least 1.")
        try:
            response = self._open(
                self._request(prompt, max_output_tokens), timeout=TIMEOUT_S
            )
        except urllib.error.HTTPError as e:
            raise _failure_for_status(e) from None
        except (TimeoutError, socket.timeout):
            raise providers.ProviderFailure(
                "timeout", "connection timed out", {"where": "open"}
            ) from None
        except (
            urllib.error.URLError,
            http.client.HTTPException,
            ConnectionError,
            OSError,
        ) as e:
            raise providers.ProviderFailure(
                "transport_error",
                "could not connect",
                {"where": "open", "exception": type(e).__name__},
            ) from None

        headers = getattr(response, "headers", None)
        request_id = headers.get("x-request-id") if headers else None
        provider_request_id = _provider_request_id(headers)
        # Identifies the HTTP response in every diagnostic raised below.
        stream_info = {"http_status": _safe(getattr(response, "status", None))}
        if request_id is not None:
            stream_info["request_id"] = _safe(request_id)

        def failure(
            category: str, where: str, **extra: str
        ) -> providers.ProviderFailure:
            return providers.ProviderFailure(
                category,
                where,
                {"where": where, **stream_info, **extra},
                provider_request_id,
            )

        def rejected(where: str, error: dict) -> RequestRejected:
            return RequestRejected(
                200, {"where": where, **stream_info, **_error_fields(error)}
            )

        with response:
            try:
                for event in _events(iter(response.readline, b"")):
                    kind = event.get("type")
                    if kind == "response.output_text.delta":
                        delta = event.get("delta")
                        if not isinstance(delta, str):
                            raise providers.ProviderFailure(
                                "invalid_response", "delta is not text"
                            )
                        yield delta
                    elif kind == "response.completed":
                        yield _usage(event.get("response"), provider_request_id)
                        return
                    elif kind == "response.incomplete":
                        final = event.get("response") or {}
                        details = final.get("incomplete_details") or {}
                        reason = details.get("reason")
                        if reason != "max_output_tokens":
                            raise failure(
                                "provider_error",
                                "event:response.incomplete",
                                incomplete_reason=_safe(reason),
                            )
                        yield _usage(final, provider_request_id)
                        return
                    elif kind == "response.failed":
                        final = event.get("response") or {}
                        error = final.get("error")
                        if _is_account_error(error):
                            raise rejected("event:response.failed", error)
                        raise failure(
                            "provider_error",
                            "event:response.failed",
                            response_status=_safe(final.get("status")),
                            **_error_fields(error),
                        )
                    elif kind == "error":
                        error = _error_event_details(event)
                        if _is_account_error(error):
                            raise rejected("event:error", error)
                        code = str(error.get("code") or "")
                        category = (
                            "rate_limited"
                            if "rate_limit" in code
                            else "provider_error"
                        )
                        raise failure(
                            category, "event:error", **_error_fields(error)
                        )
            except providers.ProviderFailure as e:
                # Failures raised by helpers that do not know the response
                # (e.g. invalid_response from _events or _usage) still get the
                # response's identifiers.
                if not e.diagnostics:
                    e.diagnostics = {"where": "stream", **stream_info}
                if e.provider_request_id is None:
                    e.provider_request_id = provider_request_id
                raise
            except (TimeoutError, socket.timeout):
                raise failure("timeout", "stream_read") from None
            except (http.client.HTTPException, ConnectionError, OSError) as e:
                raise failure(
                    "transport_error", "stream_read", exception=type(e).__name__
                ) from None
            except UnicodeDecodeError:
                raise failure("invalid_response", "stream_decode") from None
