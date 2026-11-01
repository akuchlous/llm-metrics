"""HTTP streaming helpers shared by the real provider adapters.

Owns only behavior that is identical for every provider: sending one request
without retry, mapping connection and read errors to failure categories,
parsing server-sent events, and sanitizing values for diagnostics. What a
provider's events, usage, statuses and error codes mean stays in its adapter.

Privacy: nothing here returns or raises free text from a provider. Diagnostics
and ids pass through `safe`/`safe_id`, which accept only short identifier-like
tokens, so messages, prompts, response text and secrets cannot leak through
them. Error bodies are read (bounded) only by adapters, to find error codes.
"""

from collections.abc import Callable, Iterator
import contextlib
import http.client
import json
import re
import socket
import urllib.error
import urllib.request

from llm_metrics import providers

TIMEOUT_S = 60  # Connect and per-read socket timeout, not a total deadline.
# An HTTP error body is read only to find its error code, so cap the read.
ERROR_BODY_LIMIT = 64 * 1024
_SAFE_TOKEN = re.compile(r"[A-Za-z0-9_.:/-]{1,100}")


def safe(value) -> str:
    """Returns `value` if it is a short identifier-like token.

    Returns "<none>" for None and "<redacted>" for anything else (free text,
    booleans, long values), so diagnostics never carry provider wording.
    """
    if value is None:
        return "<none>"
    if isinstance(value, bool):
        return "<redacted>"
    text = str(value)
    return text if _SAFE_TOKEN.fullmatch(text) else "<redacted>"


def safe_id(value) -> str | None:
    """Returns `value` if it is a safe identifier string, else None.

    Never returns a redaction marker: a marker is not an id and must not be
    stored as one.
    """
    if isinstance(value, str) and _SAFE_TOKEN.fullmatch(value):
        return value
    return None


def is_count(value) -> bool:
    """Whether `value` is a non-negative int (booleans excluded)."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


class RequestRejected(Exception):
    """The provider rejected the request itself; not a benchmark outcome.

    Raised when our key, permissions, model name, parameters, billing or
    account are wrong (e.g. HTTP 400/401/403/404, or an account-credit error).
    Such failures say nothing about the provider's reliability, so callers
    must not record the attempt.

    Attributes:
        status: HTTP status (200 when the rejection arrived inside a stream).
        diagnostics: Sanitized identifiers for `--debug`; never stored.
    """

    provider_label = "The provider"

    def __init__(self, status: int, diagnostics: dict[str, str] | None = None):
        super().__init__(
            f"{self.provider_label} rejected the request (HTTP {status})."
        )
        self.status = status
        self.diagnostics = diagnostics or {}


def read_error_body(error: urllib.error.HTTPError) -> dict | None:
    """Returns an HTTP error's JSON body (bounded read), or None.

    The caller extracts error codes and then discards the body; it is never
    stored, printed or put in an exception message.
    """
    try:
        body = json.loads(error.read(ERROR_BODY_LIMIT) or b"{}")
    except (ValueError, OSError):
        return None
    return body if isinstance(body, dict) else None


def post_json(url: str, body: dict, headers: dict[str, str]):
    """Builds a streaming JSON POST request (the key travels in `headers`)."""
    return urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            **headers,
        },
    )


def open_stream(
    opener: Callable,
    request: urllib.request.Request,
    failure_for_status: Callable[[urllib.error.HTTPError], Exception],
):
    """Sends `request` exactly once and returns the open response.

    Args:
        opener: `urllib.request.urlopen`-compatible callable (injectable so
            tests never touch the network).
        request: The request to send.
        failure_for_status: Maps an HTTP error status to the provider's
            `ProviderFailure` or `RequestRejected`.

    Raises:
        ProviderFailure: "timeout" or "transport_error" when no response
            arrives, or the mapped failure for an HTTP error status.
        RequestRejected: When the status means our request is at fault.
    """
    try:
        return opener(request, timeout=TIMEOUT_S)
    except urllib.error.HTTPError as e:
        raise failure_for_status(e) from None
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


@contextlib.contextmanager
def read_failures(
    failure: Callable[..., providers.ProviderFailure],
) -> Iterator[None]:
    """Maps errors while reading an open stream to failure categories.

    Args:
        failure: The adapter's `failure(category, where, **extra)` factory,
            which adds the response's identifiers.

    Raises:
        ProviderFailure: "timeout" for a read timeout, "transport_error" for a
            dropped connection, "invalid_response" for undecodable bytes.
    """
    try:
        yield
    except (TimeoutError, socket.timeout):
        raise failure("timeout", "stream_read") from None
    except (http.client.HTTPException, ConnectionError, OSError) as e:
        raise failure(
            "transport_error", "stream_read", exception=type(e).__name__
        ) from None
    except UnicodeDecodeError:
        raise failure("invalid_response", "stream_decode") from None


def sse_events(lines: Iterator[bytes]) -> Iterator[dict]:
    """Parses server-sent events: one JSON object per event, in `data:` lines.

    Other SSE fields ("event:", "id:", comments) are skipped: every provider
    used here repeats the event type inside the JSON. Stops at a `[DONE]`
    payload.

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
