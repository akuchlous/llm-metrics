"""Anthropic provider: one streamed Messages API call, standard library only.

Sends `POST https://api.anthropic.com/v1/messages` (`anthropic-version:
2023-06-01`, `stream: true`) with the workload prompt as the single user
message, the output cap as `max_tokens`, and the settings of `PROFILE`
(thinking disabled). No system prompt is added. The server-sent events are
translated into the `LLMProvider` contract:

- `content_block_delta` with a `text_delta`: its text, as one chunk. Thinking
  deltas, block starts/stops, `ping` and `message_start` are not output.
- `message_start`: its `usage` gives the input token counts.
- `message_delta`: its `usage` is cumulative, so the last one gives the final
  output tokens (and, when present, updated input counts); `delta.stop_reason`
  says why generation stopped.
- `message_stop`: the end of a complete response: the final `Usage`.

Usage normalization: Anthropic's `input_tokens` excludes tokens read from or
written to the prompt cache, while `providers.Usage.input_tokens` is the whole
prompt. So input_tokens = input_tokens + cache_read_input_tokens +
cache_creation_input_tokens, and cached_input_tokens = cache_read_input_tokens
(None when not reported). Reported values are never altered otherwise.
Output tokens include any thinking tokens (billed as output); with thinking
disabled there are none.

Stop reasons `end_turn`, `max_tokens` (the cap is a valid stopping point) and
`stop_sequence` complete a response. Any other (e.g. `refusal`) is recorded as
a `provider_error` with the sanitized reason in diagnostics.

Error mapping happens here, at the provider boundary: HTTP 429 and
`rate_limit_error` events -> rate_limited; 408/504 and `timeout_error` ->
timeout; other 5xx (including 529 overloaded) and `api_error` /
`overloaded_error` events -> provider_error. Our own request or account
problems (other 4xx, including 402 billing, and authentication, permission,
billing or invalid-request error events) raise `RequestRejected` and are not
recorded. Limitation: Anthropic also returns 429 when the organization's
monthly spend cap is reached; that cannot be told apart from a rate limit
reliably, so it is recorded as rate_limited.

The request id is the `request-id` response header. Privacy and no-retry rules
are those of `openai_provider`.
"""

from collections.abc import Callable, Iterator
import urllib.error
import urllib.request

from llm_metrics import http_streaming
from llm_metrics import providers
from llm_metrics import targets

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
PROFILE = targets.ANTHROPIC
_COMPLETE_STOP_REASONS = frozenset({"end_turn", "max_tokens", "stop_sequence"})
# Error types meaning our request, key or account is wrong.
_REJECTED_ERROR_TYPES = frozenset(
    {
        "invalid_request_error",
        "authentication_error",
        "billing_error",
        "permission_error",
        "not_found_error",
        "request_too_large",
    }
)


class RequestRejected(http_streaming.RequestRejected):
    """Anthropic rejected the request itself; not a benchmark outcome."""

    provider_label = "Anthropic"


def _error_fields(error) -> dict[str, str]:
    """Returns the sanitized type of an Anthropic error object (no message)."""
    if not isinstance(error, dict) or "type" not in error:
        return {}
    return {"error_type": http_streaming.safe(error["type"])}


def _failure_for_status(
    error: urllib.error.HTTPError,
) -> providers.ProviderFailure | RequestRejected:
    """Maps an HTTP error status to a recorded failure or a rejection."""
    status = error.code
    request_id = http_streaming.safe_id(
        error.headers.get("request-id") if error.headers else None
    )
    diagnostics = {
        "where": "http_status",
        "http_status": http_streaming.safe(status),
    }
    if request_id is not None:
        diagnostics["request_id"] = request_id
    body = http_streaming.read_error_body(error)
    diagnostics.update(_error_fields(body.get("error") if body else None))
    if status == 429:
        category = "rate_limited"
    elif status in (408, 504):
        category = "timeout"
    elif status >= 500:
        category = "provider_error"
    else:
        return RequestRejected(status, diagnostics)
    return providers.ProviderFailure(
        category, f"HTTP {status}", diagnostics, request_id
    )


def _count(usage: dict, key: str, required: bool) -> int | None:
    """Returns a usage count, None if absent and optional.

    Raises:
        ProviderFailure: "invalid_response" if a required count is missing or
            any present count is not a non-negative integer.
    """
    value = usage.get(key)
    if value is None and not required:
        return None
    if not http_streaming.is_count(value):
        raise providers.ProviderFailure(
            "invalid_response", f"usage {key} is not a count"
        )
    return value


class AnthropicProvider(providers.LLMProvider):
    """Streams one Anthropic Messages API request per `stream()` call.

    The API key exists only in the request's `x-api-key` header and is never
    shown by `repr` or stored.
    """

    name = PROFILE.provider
    model = PROFILE.model
    cache_policy = PROFILE.cache_policy
    request_profile = PROFILE

    def __init__(self, api_key: str, opener: Callable = urllib.request.urlopen):
        """Initializes the provider.

        Args:
            api_key: Anthropic API key.
            opener: `urllib.request.urlopen`-compatible callable. Injectable so
                tests never touch the network.

        Raises:
            ValueError: If `api_key` is empty.
        """
        if not api_key:
            raise ValueError("An Anthropic API key is required.")
        self._api_key = api_key
        self._open = opener

    def __repr__(self) -> str:
        return f"AnthropicProvider(model={self.model!r})"

    def _request(
        self, prompt: str, max_output_tokens: int
    ) -> urllib.request.Request:
        body = PROFILE.apply_settings(
            {
                "model": self.model,
                "max_tokens": max_output_tokens,
                # The smallest neutral wrapper: one user message, no system.
                "messages": [{"role": "user", "content": prompt}],
                "stream": True,
            }
        )
        return http_streaming.post_json(
            API_URL,
            body,
            {"x-api-key": self._api_key, "anthropic-version": API_VERSION},
        )

    def stream(
        self, prompt: str, max_output_tokens: int
    ) -> Iterator[str | providers.Usage]:
        """Sends one request and streams its response.

        See `providers.LLMProvider.stream`. A stream that ends before
        `message_stop` yields no `Usage` and is recorded as invalid_response.

        Raises:
            ValueError: If `max_output_tokens` is less than 1.
            ProviderFailure: For provider-side failures.
            RequestRejected: When the request, key, or account is at fault;
                the attempt must not be recorded.
        """
        if max_output_tokens < 1:
            raise ValueError("max_output_tokens must be at least 1.")
        response = http_streaming.open_stream(
            self._open,
            self._request(prompt, max_output_tokens),
            _failure_for_status,
        )
        headers = getattr(response, "headers", None)
        provider_request_id = http_streaming.safe_id(
            headers.get("request-id") if headers else None
        )
        stream_info = {
            "http_status": http_streaming.safe(
                getattr(response, "status", None)
            )
        }
        if provider_request_id is not None:
            stream_info["request_id"] = provider_request_id

        def failure(
            category: str, where: str, **extra: str
        ) -> providers.ProviderFailure:
            return providers.ProviderFailure(
                category,
                where,
                {"where": where, **stream_info, **extra},
                provider_request_id,
            )

        usage: dict = {}
        stop_reason = None
        with response, http_streaming.read_failures(failure):
            try:
                for event in http_streaming.sse_events(
                    iter(response.readline, b"")
                ):
                    kind = event.get("type")
                    if kind == "content_block_delta":
                        delta = event.get("delta") or {}
                        if delta.get("type") == "text_delta":
                            text = delta.get("text")
                            if not isinstance(text, str):
                                raise failure(
                                    "invalid_response", "event:text_delta"
                                )
                            yield text
                    elif kind == "message_start":
                        message = event.get("message") or {}
                        usage.update(message.get("usage") or {})
                    elif kind == "message_delta":
                        # Cumulative counts: later values replace earlier.
                        usage.update(event.get("usage") or {})
                        stop_reason = (event.get("delta") or {}).get(
                            "stop_reason", stop_reason
                        )
                    elif kind == "message_stop":
                        if stop_reason not in _COMPLETE_STOP_REASONS:
                            raise failure(
                                "provider_error",
                                "event:message_stop",
                                stop_reason=http_streaming.safe(stop_reason),
                            )
                        yield self._usage(usage, provider_request_id)
                        return
                    elif kind == "error":
                        error = event.get("error") or {}
                        error_type = error.get("type")
                        if error_type in _REJECTED_ERROR_TYPES:
                            raise RequestRejected(
                                200,
                                {
                                    "where": "event:error",
                                    **stream_info,
                                    **_error_fields(error),
                                },
                            )
                        category = {
                            "rate_limit_error": "rate_limited",
                            "timeout_error": "timeout",
                        }.get(error_type, "provider_error")
                        raise failure(
                            category, "event:error", **_error_fields(error)
                        )
            except providers.ProviderFailure as e:
                if not e.diagnostics:
                    e.diagnostics = {"where": "stream", **stream_info}
                if e.provider_request_id is None:
                    e.provider_request_id = provider_request_id
                raise

    @staticmethod
    def _usage(usage: dict, provider_request_id: str | None) -> providers.Usage:
        """Builds the final `Usage` from the accumulated usage fields.

        Raises:
            ProviderFailure: "invalid_response" if input or output tokens are
                missing or any count is malformed.
        """
        uncached = _count(usage, "input_tokens", required=True)
        output = _count(usage, "output_tokens", required=True)
        cache_read = _count(usage, "cache_read_input_tokens", required=False)
        cache_write = _count(
            usage, "cache_creation_input_tokens", required=False
        )
        return providers.Usage(
            input_tokens=uncached + (cache_read or 0) + (cache_write or 0),
            output_tokens=output,
            provider_request_id=provider_request_id,
            cached_input_tokens=cache_read,
        )
