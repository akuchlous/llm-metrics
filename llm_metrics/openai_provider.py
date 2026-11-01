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
import urllib.error
import urllib.request

from llm_metrics import http_streaming
from llm_metrics import providers
from llm_metrics import targets

API_URL = "https://api.openai.com/v1/responses"
# The benchmark target: model and every deliberate request setting
# (`store: false`, `reasoning.effort: "none"`, prompt caching disabled through
# explicit cache mode without breakpoints). Sources are in DECISIONS.md
# (D047, D052, D062). If OpenAI rejected a setting, the request would fail
# with HTTP 400 (RequestRejected, not recorded; `--debug` shows error_param).
PROFILE = targets.OPENAI
# Error codes/types meaning our account cannot pay, not that OpenAI failed.
_ACCOUNT_ERRORS = frozenset({"insufficient_quota", "credit_balance_exhausted"})


def _error_fields(error) -> dict[str, str]:
    """Returns the sanitized code/type/param of an OpenAI error object.

    The message is deliberately dropped. Returns {} if `error` is not a dict.
    """
    if not isinstance(error, dict):
        return {}
    return {
        f"error_{key}": http_streaming.safe(error[key])
        for key in ("code", "type", "param")
        if key in error
    }


def _request_id(headers):
    """Returns OpenAI's raw `x-request-id` header value, or None."""
    return headers.get("x-request-id") if headers else None


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


class RequestRejected(http_streaming.RequestRejected):
    """OpenAI rejected the request itself; not a benchmark outcome.

    Raised for HTTP 400/401/403/404 and other non-retryable client errors, and
    for account-credit errors. See `http_streaming.RequestRejected`.
    """

    provider_label = "OpenAI"


def _http_error_diagnostics(
    error: urllib.error.HTTPError,
) -> tuple[dict[str, str], bool]:
    """Extracts sanitized diagnostics from an HTTP error response.

    The body is read (bounded) only to find the error code/type/param and is
    then discarded.

    Returns:
        (diagnostics, is_account_error).
    """
    diagnostics = {
        "where": "http_status",
        "http_status": http_streaming.safe(error.code),
    }
    request_id = _request_id(error.headers)
    if request_id is not None:
        diagnostics["request_id"] = http_streaming.safe(request_id)
    body = http_streaming.read_error_body(error)
    error_object = body.get("error") if isinstance(body, dict) else None
    diagnostics.update(_error_fields(error_object))
    return diagnostics, _is_account_error(error_object)


def _failure_for_status(
    error: urllib.error.HTTPError,
) -> providers.ProviderFailure | RequestRejected:
    """Maps an HTTP error status to a recorded failure or a rejection."""
    diagnostics, account_error = _http_error_diagnostics(error)
    if account_error:
        return RequestRejected(error.code, diagnostics)
    return http_streaming.status_failure(
        error.code,
        diagnostics,
        RequestRejected,
        http_streaming.safe_id(_request_id(error.headers)),
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
    if not isinstance(usage, dict):
        raise providers.ProviderFailure(
            "invalid_response", "final event without usage"
        )
    details = usage.get("input_tokens_details")
    return http_streaming.checked_usage(
        usage.get("input_tokens"),
        usage.get("output_tokens"),
        details.get("cached_tokens") if isinstance(details, dict) else None,
        provider_request_id,
    )


class OpenAIProvider(providers.LLMProvider):
    """Streams one OpenAI Responses API request per `stream()` call.

    Every request sends the settings of `PROFILE` (prompt caching disabled),
    so `cache_policy` is "disabled". The API key exists only in the request's
    Authorization header and is never shown by `repr` or stored.
    """

    name = PROFILE.provider
    model = PROFILE.model
    cache_policy = PROFILE.cache_policy
    request_profile = PROFILE

    def __init__(self, api_key: str, opener: Callable = urllib.request.urlopen):
        """Initializes the provider.

        Args:
            api_key: OpenAI API key.
            opener: `urllib.request.urlopen`-compatible callable. Injectable so
                tests never touch the network.

        Raises:
            ValueError: If `api_key` is empty.
        """
        if not api_key:
            raise ValueError("An OpenAI API key is required.")
        self._api_key = api_key
        self._open = opener

    def __repr__(self) -> str:
        return f"OpenAIProvider(model={self.model!r})"

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
        response = http_streaming.open_stream(
            self._open,
            self._request(prompt, max_output_tokens),
            _failure_for_status,
        )

        context = http_streaming.StreamContext(
            response, _request_id(getattr(response, "headers", None))
        )

        def rejected(where: str, error: dict) -> RequestRejected:
            return RequestRejected(
                200, {"where": where, **context.info, **_error_fields(error)}
            )

        with response, context.reading():
            for event in http_streaming.sse_events(
                iter(response.readline, b"")
            ):
                kind = event.get("type")
                if kind == "response.output_text.delta":
                    delta = event.get("delta")
                    if not isinstance(delta, str):
                        raise providers.ProviderFailure(
                            "invalid_response", "delta is not text"
                        )
                    yield delta
                elif kind == "response.completed":
                    yield _usage(
                        event.get("response"), context.provider_request_id
                    )
                    return
                elif kind == "response.incomplete":
                    final = event.get("response") or {}
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
                    final = event.get("response") or {}
                    error = final.get("error")
                    if _is_account_error(error):
                        raise rejected("event:response.failed", error)
                    raise context.failure(
                        "provider_error",
                        "event:response.failed",
                        response_status=http_streaming.safe(
                            final.get("status")
                        ),
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
                    raise context.failure(
                        category, "event:error", **_error_fields(error)
                    )
