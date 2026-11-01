"""xAI provider: one streamed Responses API call, standard library only.

Sends `POST https://api.x.ai/v1/responses` with `stream: true`, the workload
prompt as the plain-text `input`, the output cap as `max_output_tokens`, and
the settings of `PROFILE` (`store: false`). The model is a non-reasoning
variant, so no `reasoning` field is sent; no instructions are added.

xAI's Responses API follows OpenAI's event shapes, but this adapter is kept
separate from `openai_provider` because the request settings, cache behavior,
request ids and error codes differ. Events:

- `response.output_text.delta`: its text, as one chunk. Other events
  (`response.created`, item and part events, reasoning events) are not output.
- `response.completed`: the final `Usage` from the response's `usage`.
- `response.incomplete` because `max_output_tokens` was reached: also a final
  `Usage` (the cap is a valid stopping point); any other reason is a
  provider_error.
- `response.failed` and `error`: failures (see below).

Usage: input_tokens = `usage.input_tokens` (including cached tokens, which
xAI bills at the cached rate), cached_input_tokens =
`usage.input_tokens_details.cached_tokens` (None when absent), output_tokens =
`usage.output_tokens` (including any reasoning tokens). xAI caches prompts
automatically and documents no way to turn that off, so cached tokens can be
reported even on a benchmark request; they are recorded, never assumed.

Error mapping happens here, at the provider boundary: HTTP 429 and error codes
naming a rate limit -> rate_limited; 408/504 -> timeout; other 5xx,
`response.failed` and other error events -> provider_error. Our own request,
key, team or credit problems (other 4xx, including 401/403) raise
`RequestRejected` and are not recorded.

The provider request id is the response's `id` from the stream; xAI documents
no request-id header. Privacy and no-retry rules are those of
`openai_provider`.
"""

from collections.abc import Callable, Iterator
import urllib.error
import urllib.request

from llm_metrics import http_streaming
from llm_metrics import providers
from llm_metrics import targets

API_URL = "https://api.x.ai/v1/responses"
PROFILE = targets.XAI


class RequestRejected(http_streaming.RequestRejected):
    """xAI rejected the request itself; not a benchmark outcome."""

    provider_label = "xAI"


def _error_fields(error) -> dict[str, str]:
    """Returns the sanitized code/type of an xAI error object (no message)."""
    if not isinstance(error, dict):
        return {}
    return {
        f"error_{key}": http_streaming.safe(error[key])
        for key in ("code", "type")
        if key in error
    }


def _failure_for_status(
    error: urllib.error.HTTPError,
) -> providers.ProviderFailure | RequestRejected:
    """Maps an HTTP error status to a recorded failure or a rejection."""
    diagnostics = {
        "where": "http_status",
        "http_status": http_streaming.safe(error.code),
    }
    body = http_streaming.read_error_body(error)
    diagnostics.update(_error_fields(body.get("error") if body else None))
    return http_streaming.status_failure(
        error.code, diagnostics, RequestRejected
    )


def _usage(response, provider_request_id: str | None) -> providers.Usage:
    """Builds the final `Usage` from a final response object.

    Raises:
        ProviderFailure: "invalid_response" if usage is missing or malformed.
    """
    usage = response.get("usage") if isinstance(response, dict) else None
    if not isinstance(usage, dict):
        raise providers.ProviderFailure("invalid_response", "no usage")
    details = usage.get("input_tokens_details")
    return http_streaming.checked_usage(
        usage.get("input_tokens"),
        usage.get("output_tokens"),
        details.get("cached_tokens") if isinstance(details, dict) else None,
        provider_request_id,
    )


class XAIProvider(providers.LLMProvider):
    """Streams one xAI Responses API request per `stream()` call.

    The API key exists only in the request's Authorization header and is never
    shown by `repr` or stored.
    """

    name = PROFILE.provider
    model = PROFILE.model
    cache_policy = PROFILE.cache_policy
    request_profile = PROFILE

    def __init__(self, api_key: str, opener: Callable = urllib.request.urlopen):
        """Initializes the provider.

        Args:
            api_key: xAI API key.
            opener: `urllib.request.urlopen`-compatible callable. Injectable so
                tests never touch the network.

        Raises:
            ValueError: If `api_key` is empty.
        """
        if not api_key:
            raise ValueError("An xAI API key is required.")
        self._api_key = api_key
        self._open = opener

    def __repr__(self) -> str:
        return f"XAIProvider(model={self.model!r})"

    def _request(
        self, prompt: str, max_output_tokens: int
    ) -> urllib.request.Request:
        body = PROFILE.apply_settings(
            {
                "model": self.model,
                "input": prompt,
                "max_output_tokens": max_output_tokens,
                "stream": True,
            }
        )
        return http_streaming.post_json(
            API_URL, body, {"Authorization": f"Bearer {self._api_key}"}
        )

    def stream(
        self, prompt: str, max_output_tokens: int
    ) -> Iterator[str | providers.Usage]:
        """Sends one request and streams its response.

        See `providers.LLMProvider.stream`. A stream that ends without a final
        event yields no `Usage` and is recorded as invalid_response.

        Raises:
            ValueError: If `max_output_tokens` is less than 1.
            ProviderFailure: For provider-side failures.
            RequestRejected: When the request, key, team, or credit is at
                fault; the attempt must not be recorded.
        """
        if max_output_tokens < 1:
            raise ValueError("max_output_tokens must be at least 1.")
        response = http_streaming.open_stream(
            self._open,
            self._request(prompt, max_output_tokens),
            _failure_for_status,
        )
        # xAI documents no request-id header: the response id arrives in the
        # stream.
        context = http_streaming.StreamContext(response)
        with response, context.reading():
            for event in http_streaming.sse_events(
                iter(response.readline, b"")
            ):
                kind = event.get("type")
                final = event.get("response")
                if isinstance(final, dict):
                    context.set_request_id(final.get("id"))
                else:
                    final = {}
                if kind == "response.output_text.delta":
                    delta = event.get("delta")
                    if not isinstance(delta, str):
                        raise context.failure(
                            "invalid_response", "event:output_text.delta"
                        )
                    yield delta
                elif kind == "response.completed":
                    yield _usage(final, context.provider_request_id)
                    return
                elif kind == "response.incomplete":
                    details = final.get("incomplete_details") or {}
                    reason = details.get("reason")
                    if reason != "max_output_tokens":
                        raise context.failure(
                            "provider_error",
                            "event:response.incomplete",
                            incomplete_reason=http_streaming.safe(reason),
                        )
                    yield _usage(final, context.provider_request_id)
                    return
                elif kind == "response.failed":
                    raise context.failure(
                        "provider_error",
                        "event:response.failed",
                        **_error_fields(final.get("error")),
                    )
                elif kind == "error":
                    error = event.get("error")
                    if not isinstance(error, dict):
                        error = {k: v for k, v in event.items() if k != "type"}
                    code = str(error.get("code") or "")
                    category = (
                        "rate_limited"
                        if "rate_limit" in code
                        else "provider_error"
                    )
                    raise context.failure(
                        category, "event:error", **_error_fields(error)
                    )
