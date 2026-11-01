"""Google provider: one streamed Gemini Interactions API call, standard library.

Sends `POST https://generativelanguage.googleapis.com/v1beta/interactions
?alt=sse` with `stream: true`, the workload prompt as the plain-text `input`,
the output cap as `generation_config.max_output_tokens`, and the settings of
`PROFILE` (`store: false`, `thinking_level: "minimal"`). No system instruction
is added. The Interactions API is the one Google recommends for new work
(`generateContent` remains supported but is labelled legacy in the docs). The
server-sent events are translated into the `LLMProvider` contract:

- `step.delta` whose `delta.type` is "text": its text, as one chunk. Thought
  steps (`thought_summary`, `thought_signature` deltas), `interaction.created`,
  `interaction.status_update`, `step.start` and `step.stop` are not output.
- `interaction.completed`: the final interaction with `status` and `usage`.
  Status "completed" is a complete response. Status "incomplete" (which the
  API documents for, e.g., hitting max tokens, without a reason field) counts
  as a complete response only when the reported output reached the requested
  cap; otherwise it is a provider_error.

Usage normalization: input_tokens = `total_input_tokens` (the whole prompt,
including any cached part), cached_input_tokens = `total_cached_tokens` (None
when absent: "not reported" is never turned into 0). Thinking tokens are
billed as output ("response pricing is the sum of output tokens and thinking
tokens") and count against `max_output_tokens`, so output_tokens =
`total_output_tokens` + `total_thought_tokens`. Google's JSON omits
zero-valued counts, so an absent `total_thought_tokens` counts as 0; an
absent `total_output_tokens` is malformed.

Error mapping happens here, at the provider boundary: HTTP 429 and error
events whose code names a rate limit or quota -> rate_limited; 408/504 and
deadline/timeout codes -> timeout; other 5xx and error events ->
provider_error. Our own request, key, billing or project problems (other 4xx,
including 402 payment_required, 400 failed_precondition, 403
permission_denied) raise `RequestRejected` and are not recorded.

The provider request id is the interaction's `id` from the stream (Google
documents no request-id header). The API key travels only in the
`x-goog-api-key` header, never in the URL. Privacy and no-retry rules are
those of `openai_provider`.
"""

from collections.abc import Callable, Iterator
import urllib.error
import urllib.request

from llm_metrics import http_streaming
from llm_metrics import providers
from llm_metrics import targets

API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/interactions?alt=sse"
)
PROFILE = targets.GOOGLE
# Error codes (substrings, lowercase) that identify each recorded category.
_RATE_LIMIT_CODES = ("rate_limit", "quota", "too_many_requests")
_TIMEOUT_CODES = ("deadline", "timeout")
# Error codes meaning our request, key, billing or project is wrong.
_REJECTED_CODES = (
    "authentication",
    "payment_required",
    "failed_precondition",
    "permission_denied",
    "invalid",
    "not_found",
    "parameter_unknown",
)


class RequestRejected(http_streaming.RequestRejected):
    """Google rejected the request itself; not a benchmark outcome."""

    provider_label = "Google"


def _error_fields(error) -> dict[str, str]:
    """Returns the sanitized code/status of a Google error (no message)."""
    if not isinstance(error, dict):
        return {}
    return {
        f"error_{key}": http_streaming.safe(error[key])
        for key in ("code", "status")
        if key in error
    }


def _error_code(error) -> str:
    """Returns the error's code and status as lowercase text for matching."""
    if not isinstance(error, dict):
        return ""
    return f"{error.get('code') or ''} {error.get('status') or ''}".lower()


def _failure_for_status(
    error: urllib.error.HTTPError,
) -> providers.ProviderFailure | RequestRejected:
    """Maps an HTTP error status to a recorded failure or a rejection."""
    status = error.code
    diagnostics = {
        "where": "http_status",
        "http_status": http_streaming.safe(status),
    }
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
    return providers.ProviderFailure(category, f"HTTP {status}", diagnostics)


def _usage(
    interaction: dict, max_output_tokens: int, provider_request_id: str | None
) -> providers.Usage:
    """Builds the final `Usage` from a completed interaction.

    Raises:
        ProviderFailure: "invalid_response" for missing or malformed usage;
            "provider_error" for an incomplete interaction that did not reach
            the cap, or any status other than completed/incomplete.
    """
    usage = interaction.get("usage")
    if not isinstance(usage, dict):
        raise providers.ProviderFailure("invalid_response", "no usage")
    input_tokens = usage.get("total_input_tokens")
    output_tokens = usage.get("total_output_tokens")
    thought_tokens = usage.get("total_thought_tokens", 0)
    cached = usage.get("total_cached_tokens")
    for count in (input_tokens, output_tokens, thought_tokens):
        if not http_streaming.is_count(count):
            raise providers.ProviderFailure(
                "invalid_response", "usage counts are not non-negative integers"
            )
    if cached is not None and not (
        http_streaming.is_count(cached) and cached <= input_tokens
    ):
        raise providers.ProviderFailure(
            "invalid_response", "cached tokens are not a count within input"
        )
    billed_output = output_tokens + thought_tokens
    status = interaction.get("status")
    if status == "incomplete" and billed_output < max_output_tokens:
        raise providers.ProviderFailure(
            "provider_error",
            "incomplete before the cap",
            {"where": "event:interaction.completed", "status": "incomplete"},
        )
    if status not in ("completed", "incomplete"):
        raise providers.ProviderFailure(
            "provider_error",
            "interaction not completed",
            {
                "where": "event:interaction.completed",
                "status": http_streaming.safe(status),
            },
        )
    return providers.Usage(
        input_tokens=input_tokens,
        output_tokens=billed_output,
        provider_request_id=provider_request_id,
        cached_input_tokens=cached,
    )


class GoogleProvider(providers.LLMProvider):
    """Streams one Gemini Interactions API request per `stream()` call.

    The API key exists only in the request's `x-goog-api-key` header and is
    never shown by `repr` or stored.
    """

    name = PROFILE.provider
    model = PROFILE.model
    cache_policy = PROFILE.cache_policy
    request_profile = PROFILE

    def __init__(self, api_key: str, opener: Callable = urllib.request.urlopen):
        """Initializes the provider.

        Args:
            api_key: Gemini API key.
            opener: `urllib.request.urlopen`-compatible callable. Injectable so
                tests never touch the network.

        Raises:
            ValueError: If `api_key` is empty.
        """
        if not api_key:
            raise ValueError("A Gemini API key is required.")
        self._api_key = api_key
        self._open = opener

    def __repr__(self) -> str:
        return f"GoogleProvider(model={self.model!r})"

    def _request(
        self, prompt: str, max_output_tokens: int
    ) -> urllib.request.Request:
        body = PROFILE.apply_settings(
            {
                "model": self.model,
                "input": prompt,
                "generation_config": {"max_output_tokens": max_output_tokens},
                "stream": True,
            }
        )
        return http_streaming.post_json(
            API_URL, body, {"x-goog-api-key": self._api_key}
        )

    def stream(
        self, prompt: str, max_output_tokens: int
    ) -> Iterator[str | providers.Usage]:
        """Sends one request and streams its response.

        See `providers.LLMProvider.stream`. A stream that ends before
        `interaction.completed` yields no `Usage` and is recorded as
        invalid_response.

        Raises:
            ValueError: If `max_output_tokens` is less than 1.
            ProviderFailure: For provider-side failures.
            RequestRejected: When the request, key, billing, or project is at
                fault; the attempt must not be recorded.
        """
        if max_output_tokens < 1:
            raise ValueError("max_output_tokens must be at least 1.")
        response = http_streaming.open_stream(
            self._open,
            self._request(prompt, max_output_tokens),
            _failure_for_status,
        )
        stream_info = {
            "http_status": http_streaming.safe(
                getattr(response, "status", None)
            )
        }
        provider_request_id = None

        def failure(
            category: str, where: str, **extra: str
        ) -> providers.ProviderFailure:
            return providers.ProviderFailure(
                category,
                where,
                {"where": where, **stream_info, **extra},
                provider_request_id,
            )

        with response, http_streaming.read_failures(failure):
            try:
                for event in http_streaming.sse_events(
                    iter(response.readline, b"")
                ):
                    kind = event.get("event_type")
                    if kind == "step.delta":
                        delta = event.get("delta") or {}
                        if delta.get("type") == "text":
                            text = delta.get("text")
                            if not isinstance(text, str):
                                raise failure(
                                    "invalid_response", "event:step.delta"
                                )
                            yield text
                    elif kind in (
                        "interaction.created",
                        "interaction.completed",
                    ):
                        interaction = event.get("interaction") or {}
                        provider_request_id = (
                            http_streaming.safe_id(interaction.get("id"))
                            or provider_request_id
                        )
                        if kind == "interaction.completed":
                            yield _usage(
                                interaction,
                                max_output_tokens,
                                provider_request_id,
                            )
                            return
                    elif kind == "error":
                        error = event.get("error") or {}
                        code = _error_code(error)
                        if any(c in code for c in _REJECTED_CODES):
                            raise RequestRejected(
                                200,
                                {
                                    "where": "event:error",
                                    **stream_info,
                                    **_error_fields(error),
                                },
                            )
                        if any(c in code for c in _RATE_LIMIT_CODES):
                            category = "rate_limited"
                        elif any(c in code for c in _TIMEOUT_CODES):
                            category = "timeout"
                        else:
                            category = "provider_error"
                        raise failure(
                            category, "event:error", **_error_fields(error)
                        )
            except providers.ProviderFailure as e:
                if not e.diagnostics:
                    e.diagnostics = {"where": "stream", **stream_info}
                else:
                    e.diagnostics = {**stream_info, **e.diagnostics}
                if e.provider_request_id is None:
                    e.provider_request_id = provider_request_id
                raise
