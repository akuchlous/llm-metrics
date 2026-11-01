"""Tests for the Anthropic, Google, and xAI adapters.

Each adapter is exercised with representative mocked protocol fixtures shaped
like the provider's documented stream. Every request goes through a fake
opener; no test touches the network or spends money. The OpenAI adapter has
its own tests in `test_openai_provider.py`; the checks here that apply to all
four benchmark targets include it.

`storage.load_request` returns None only for an unknown id; tests look up ids
they have just saved, so its result is subscripted directly.
"""

# pylint: disable=unsubscriptable-object

from collections.abc import Callable
import contextlib
import dataclasses
import io
import json
import pathlib
import socket
import tempfile
import unittest
import urllib.error

from llm_metrics import anthropic_provider
from llm_metrics import benchmark
from llm_metrics import google_provider
from llm_metrics import http_streaming
from llm_metrics import latency
from llm_metrics import providers
from llm_metrics import storage
from llm_metrics import targets
from llm_metrics import workloads
from llm_metrics import xai_provider

WORKLOAD = workloads.INTERACTIVE_CHAT_V1
ORIGIN = ("local", "unknown")
FAKE_KEY = "fake-test-key-NEVER-SHOW-THIS-0123456789"
SECRETISH = "free text with spaces and sk-fake"


def sse(*events):
    """Server-sent-event bytes for the given event dicts (or raw strings)."""
    out = []
    for event in events:
        payload = event if isinstance(event, str) else json.dumps(event)
        out.append(f"event: x\ndata: {payload}\n\n")
    return "".join(out).encode("utf-8")


class FakeResponse(io.BytesIO):
    """Readable like an HTTP response; optionally fails on the nth readline."""

    def __init__(self, body, headers=None, fail_on_line=None, error=None):
        super().__init__(body)
        self.headers = headers or {}
        self.status = 200
        self.fail_on_line, self.error, self.lines = fail_on_line, error, 0

    def readline(self, *args):
        self.lines += 1
        if self.fail_on_line is not None and self.lines >= self.fail_on_line:
            raise self.error
        return super().readline(*args)


class FakeOpener:

    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def __call__(self, request, timeout):
        self.calls.append((request, timeout))
        if self.error is not None:
            raise self.error
        return self.response


# --- Anthropic Messages API fixtures -------------------------------------


def anthropic_body(
    texts=("Hel", "lo"),
    input_tokens=1950,
    output_tokens=40,
    stop_reason="end_turn",
    cache_read=0,
    final=True,
):
    usage = {"input_tokens": input_tokens, "output_tokens": 1}
    if cache_read is not None:
        usage["cache_read_input_tokens"] = cache_read
        usage["cache_creation_input_tokens"] = 0
    events = [
        {
            "type": "message_start",
            "message": {"id": "msg_01", "role": "assistant", "usage": usage},
        },
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "text", "text": ""},
        },
        {"type": "ping"},
        *(
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": text},
            }
            for text in texts
        ),
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {"stop_reason": stop_reason, "stop_sequence": None},
            "usage": {"output_tokens": output_tokens},
        },
    ]
    if final:
        events.append({"type": "message_stop"})
    return sse(*events)


def anthropic_error(error_type):
    return {
        "type": "error",
        "error": {"type": error_type, "message": SECRETISH},
    }


# --- Google Interactions API fixtures ------------------------------------


def google_body(
    texts=("Hel", "lo"),
    input_tokens=2010,
    output_tokens=38,
    thought_tokens=5,
    cached=0,
    status="completed",
    final=True,
):
    usage = {
        "total_input_tokens": input_tokens,
        "total_output_tokens": output_tokens,
        "total_thought_tokens": thought_tokens,
        "total_tokens": input_tokens + output_tokens + thought_tokens,
    }
    if cached is not None:
        usage["total_cached_tokens"] = cached
    events = [
        {
            "event_type": "interaction.created",
            "interaction": {"id": "v1_abc123", "status": "in_progress"},
        },
        {"event_type": "step.start", "index": 0, "step": {"type": "thought"}},
        {
            "event_type": "step.delta",
            "index": 0,
            "delta": {"type": "thought_signature", "signature": "c2lnbmF0"},
        },
        {"event_type": "step.stop", "index": 0},
        {
            "event_type": "step.start",
            "index": 1,
            "step": {"type": "model_output"},
        },
        *(
            {
                "event_type": "step.delta",
                "index": 1,
                "delta": {"type": "text", "text": text},
            }
            for text in texts
        ),
        {"event_type": "step.stop", "index": 1},
    ]
    if final:
        events.append(
            {
                "event_type": "interaction.completed",
                "interaction": {
                    "id": "v1_abc123",
                    "status": status,
                    "usage": usage,
                },
            }
        )
        events.append("[DONE]")
    return sse(*events)


def google_error(code):
    return {
        "event_type": "error",
        "error": {"code": code, "message": SECRETISH},
    }


# --- xAI Responses API fixtures ------------------------------------------


def xai_body(
    texts=("Hel", "lo"),
    input_tokens=1987,
    output_tokens=41,
    cached=0,
    final_type="response.completed",
    reason=None,
    final=True,
):
    usage = {"input_tokens": input_tokens, "output_tokens": output_tokens}
    if cached is not None:
        usage["input_tokens_details"] = {"cached_tokens": cached}
    final_response = {"id": "resp_9f2", "status": "completed", "usage": usage}
    if reason is not None:
        final_response["incomplete_details"] = {"reason": reason}
    events = [
        {
            "type": "response.created",
            "response": {"id": "resp_9f2", "status": "in_progress"},
        },
        {"type": "response.output_item.added", "output_index": 0},
        *({"type": "response.output_text.delta", "delta": t} for t in texts),
    ]
    if final:
        events.append({"type": final_type, "response": final_response})
        events.append("[DONE]")
    return sse(*events)


def xai_error(code):
    return {"type": "error", "error": {"code": code, "message": SECRETISH}}


@dataclasses.dataclass(frozen=True)
class Spec:
    """One adapter and fixtures in its own protocol."""

    module: object
    adapter: type
    profile: targets.RequestProfile
    url: str
    body: Callable[..., bytes]  # Fixture builder for a response stream.
    request_id: str | None
    request_id_headers: dict
    rate_limit_event: dict
    provider_error_event: dict
    rejected_event: dict

    def provider(self, **opener_kwargs):
        opener = FakeOpener(**opener_kwargs)
        return self.adapter(FAKE_KEY, opener=opener), opener


SPECS = (
    Spec(
        module=anthropic_provider,
        adapter=anthropic_provider.AnthropicProvider,
        profile=targets.ANTHROPIC,
        url="https://api.anthropic.com/v1/messages",
        body=anthropic_body,
        request_id="req_011CSHoEeqs5C35K2UUqR7Fy",
        request_id_headers={"request-id": "req_011CSHoEeqs5C35K2UUqR7Fy"},
        rate_limit_event=anthropic_error("rate_limit_error"),
        provider_error_event=anthropic_error("overloaded_error"),
        rejected_event=anthropic_error("billing_error"),
    ),
    Spec(
        module=google_provider,
        adapter=google_provider.GoogleProvider,
        profile=targets.GOOGLE,
        url=(
            "https://generativelanguage.googleapis.com/v1beta/interactions"
            "?alt=sse"
        ),
        body=google_body,
        request_id="v1_abc123",
        request_id_headers={},
        rate_limit_event=google_error("rate_limit_exceeded"),
        provider_error_event=google_error("service_unavailable"),
        rejected_event=google_error("payment_required"),
    ),
    Spec(
        module=xai_provider,
        adapter=xai_provider.XAIProvider,
        profile=targets.XAI,
        url="https://api.x.ai/v1/responses",
        body=xai_body,
        request_id="resp_9f2",
        request_id_headers={},
        rate_limit_event=xai_error("rate_limit_exceeded"),
        provider_error_event=xai_error("internal_error"),
        rejected_event=None,  # xAI documents no in-stream account errors.
    ),
)
BY_PROVIDER = {spec.profile.provider: spec for spec in SPECS}


def http_error(spec, status, body=b"{}", headers=None):
    return urllib.error.HTTPError(
        spec.url, status, "error", headers or {}, io.BytesIO(body)
    )


def measure(provider, max_output_tokens=300):
    return latency.measure_request(provider, WORKLOAD.prompt, max_output_tokens)


class RequestShapeTest(unittest.TestCase):
    """Items 1-2: canonical text and cap reach the provider unchanged."""

    def sent(self, spec):
        provider, opener = spec.provider(
            response=FakeResponse(spec.body(), spec.request_id_headers)
        )
        list(provider.stream(WORKLOAD.prompt, WORKLOAD.max_output_tokens))
        self.assertEqual(len(opener.calls), 1)  # Exactly one HTTP request.
        request, timeout = opener.calls[0]
        self.assertEqual(request.full_url, spec.url)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(timeout, http_streaming.TIMEOUT_S)
        return request, json.loads(request.data)

    def test_anthropic_request_body(self):
        request, body = self.sent(BY_PROVIDER["anthropic"])
        self.assertEqual(
            body,
            {
                "model": "claude-haiku-5-5",
                "max_tokens": 300,
                "messages": [{"role": "user", "content": WORKLOAD.prompt}],
                "stream": True,
                "thinking": {"type": "disabled"},
            },
        )
        self.assertEqual(request.get_header("X-api-key"), FAKE_KEY)
        self.assertEqual(request.get_header("Anthropic-version"), "2023-06-01")

    def test_google_request_body(self):
        request, body = self.sent(BY_PROVIDER["google"])
        self.assertEqual(
            body,
            {
                "model": "gemini-3.5-flash-lite",
                "input": WORKLOAD.prompt,
                "generation_config": {
                    "max_output_tokens": 300,
                    "thinking_level": "minimal",
                },
                "stream": True,
                "store": False,
            },
        )
        self.assertEqual(request.get_header("X-goog-api-key"), FAKE_KEY)
        self.assertNotIn(FAKE_KEY, request.full_url)  # Never in the URL.

    def test_xai_request_body(self):
        request, body = self.sent(BY_PROVIDER["xai"])
        self.assertEqual(
            body,
            {
                "model": "grok-4.20-0309-non-reasoning",
                "input": WORKLOAD.prompt,
                "max_output_tokens": 300,
                "stream": True,
                "store": False,
            },
        )
        self.assertEqual(
            request.get_header("Authorization"), f"Bearer {FAKE_KEY}"
        )

    def test_no_hidden_instructions_or_sampling_parameters(self):
        for spec in SPECS:
            with self.subTest(provider=spec.profile.provider):
                _, body = self.sent(spec)
                text = json.dumps(body)
                # The prompt appears exactly once, verbatim.
                self.assertEqual(
                    text.count(json.dumps(WORKLOAD.prompt)[1:-1]), 1
                )
                for field in (
                    "system",
                    "instructions",
                    "system_instruction",
                    "temperature",
                    "top_p",
                    "top_k",
                    "tools",
                    "cache_control",
                ):
                    self.assertNotIn(f'"{field}"', text)

    def test_cap_must_be_positive(self):
        for spec in SPECS:
            with self.subTest(provider=spec.profile.provider):
                provider, opener = spec.provider()
                with self.assertRaises(ValueError):
                    list(provider.stream("p", 0))
                self.assertEqual(opener.calls, [])


class StreamTranslationTest(unittest.TestCase):
    """Items 3-7: content, first-token boundary, usage, request ids."""

    def test_text_chunks_then_authoritative_usage(self):
        expected = {
            "anthropic": providers.Usage(
                1950, 40, "req_011CSHoEeqs5C35K2UUqR7Fy", 0
            ),
            # Output includes thinking tokens: 38 + 5.
            "google": providers.Usage(2010, 43, "v1_abc123", 0),
            "xai": providers.Usage(1987, 41, "resp_9f2", 0),
        }
        for spec in SPECS:
            with self.subTest(provider=spec.profile.provider):
                provider, _ = spec.provider(
                    response=FakeResponse(spec.body(), spec.request_id_headers)
                )
                self.assertEqual(
                    list(provider.stream("p", 300)),
                    ["Hel", "lo", expected[spec.profile.provider]],
                )

    def test_metadata_before_output_is_not_first_content(self):
        # Only "Hel" and "lo" are output: role/start/ping/thought/created
        # events before them must not be yielded, so TTFT starts at "Hel".
        for spec in SPECS:
            with self.subTest(provider=spec.profile.provider):
                provider, _ = spec.provider(
                    response=FakeResponse(spec.body(), spec.request_id_headers)
                )
                items = list(provider.stream("p", 300))
                self.assertEqual(items[0], "Hel")
                self.assertTrue(all(isinstance(i, str) for i in items[:-1]))

    def test_metadata_only_stream_has_no_text_and_is_invalid(self):
        for spec in SPECS:
            with self.subTest(provider=spec.profile.provider):
                provider, _ = spec.provider(
                    response=FakeResponse(
                        spec.body(texts=()), spec.request_id_headers
                    )
                )
                attempt, results = measure(provider)
                self.assertEqual(attempt["outcome"], "invalid_response")
                self.assertEqual(results, [])

    def test_cached_tokens_reported_zero_differs_from_not_reported(self):
        for spec in SPECS:
            with self.subTest(provider=spec.profile.provider):
                for cached, expected in ((0, 0), (None, None), (64, 64)):
                    provider, _ = spec.provider(
                        response=FakeResponse(cached_body(spec, cached))
                    )
                    usage = list(provider.stream("p", 300))[-1]
                    self.assertEqual(usage.cached_input_tokens, expected)

    def test_anthropic_input_includes_cache_reads(self):
        # Anthropic's input_tokens excludes cache reads; the stored input is
        # the whole prompt, and the cached part is kept separately.
        spec = BY_PROVIDER["anthropic"]
        provider, _ = spec.provider(
            response=FakeResponse(
                anthropic_body(input_tokens=900, cache_read=1024)
            )
        )
        usage = list(provider.stream("p", 300))[-1]
        self.assertEqual(
            (usage.input_tokens, usage.cached_input_tokens), (1924, 1024)
        )

    def test_anthropic_message_delta_usage_is_cumulative(self):
        body = anthropic_body(output_tokens=7).replace(
            b'"output_tokens": 7}}',
            b'"output_tokens": 7}}\n\nevent: x\ndata: {"type":'
            b' "message_delta", "delta": {}, "usage": {"output_tokens": 9}}',
        )
        provider, _ = BY_PROVIDER["anthropic"].provider(
            response=FakeResponse(body)
        )
        self.assertEqual(list(provider.stream("p", 300))[-1].output_tokens, 9)

    def test_reaching_the_cap_is_a_complete_response(self):
        cases = {
            "anthropic": anthropic_body(
                output_tokens=300, stop_reason="max_tokens"
            ),
            "google": google_body(
                output_tokens=295, thought_tokens=5, status="incomplete"
            ),
            "xai": xai_body(
                output_tokens=300,
                final_type="response.incomplete",
                reason="max_output_tokens",
            ),
        }
        for provider_name, body in cases.items():
            with self.subTest(provider=provider_name):
                provider, _ = BY_PROVIDER[provider_name].provider(
                    response=FakeResponse(body)
                )
                attempt, _ = measure(provider)
                self.assertEqual(attempt["outcome"], "success")
                self.assertEqual(attempt["output_tokens"], 300)
                self.assertEqual(attempt["requested_max_output_tokens"], 300)

    def test_other_stops_are_provider_errors(self):
        cases = {
            "anthropic": anthropic_body(stop_reason="refusal"),
            # Incomplete well below the cap: not a cap stop.
            "google": google_body(status="incomplete"),
            "xai": xai_body(
                final_type="response.incomplete", reason="content_filter"
            ),
        }
        for provider_name, body in cases.items():
            with self.subTest(provider=provider_name):
                provider, _ = BY_PROVIDER[provider_name].provider(
                    response=FakeResponse(body)
                )
                attempt, _ = measure(provider)
                self.assertEqual(attempt["outcome"], "provider_error")
                self.assertEqual(
                    attempt["provider_request_id"],
                    BY_PROVIDER[provider_name].request_id
                    if provider_name != "anthropic"
                    else None,
                )

    def test_unsafe_request_ids_are_not_stored(self):
        cases = {
            "anthropic": FakeResponse(
                anthropic_body(), {"request-id": SECRETISH}
            ),
            "google": FakeResponse(
                google_body().replace(b"v1_abc123", b"bad id with spaces")
            ),
            "xai": FakeResponse(
                xai_body().replace(b"resp_9f2", b"bad id with spaces")
            ),
        }
        for provider_name, response in cases.items():
            with self.subTest(provider=provider_name):
                provider, _ = BY_PROVIDER[provider_name].provider(
                    response=response
                )
                attempt, _ = measure(provider)
                self.assertEqual(attempt["outcome"], "success")
                self.assertIsNone(attempt["provider_request_id"])


def cached_body(spec, cached):
    """A success body whose cached-token field is `cached` (None: absent)."""
    if spec.profile.provider == "anthropic":
        return anthropic_body(
            input_tokens=1950 - (cached or 0), cache_read=cached
        )
    return spec.body(cached=cached)


class UsageValidationTest(unittest.TestCase):
    """Item 8: malformed or incomplete streams are invalid_response."""

    def test_malformed_streams(self):
        cases = {
            "anthropic": {
                "no message_stop": anthropic_body(final=False),
                "no input usage": anthropic_body().replace(
                    b'"input_tokens": 1950, ', b""
                ),
                "negative output": anthropic_body(output_tokens=-1),
                "not JSON": anthropic_body(final=False) + b"data: {oops\n\n",
            },
            "google": {
                "no interaction.completed": google_body(final=False),
                "no output count": google_body().replace(
                    b'"total_output_tokens": 38, ', b""
                ),
                "cached above input": google_body(cached=5000),
                "text not a string": google_body(texts=(7,)),
            },
            "xai": {
                "no final event": xai_body(final=False),
                "boolean count": xai_body().replace(
                    b'"output_tokens": 41', b'"output_tokens": true'
                ),
                "cached above input": xai_body(cached=5000),
                "delta not a string": xai_body(texts=(7,)),
            },
        }
        for provider_name, bodies in cases.items():
            for name, body in bodies.items():
                with self.subTest(provider=provider_name, case=name):
                    provider, _ = BY_PROVIDER[provider_name].provider(
                        response=FakeResponse(body)
                    )
                    attempt, results = measure(provider)
                    self.assertEqual(attempt["outcome"], "invalid_response")
                    self.assertIsNone(attempt["input_tokens"])
                    self.assertEqual(results, [])

    def test_output_above_the_cap_is_invalid(self):
        for spec in SPECS:
            with self.subTest(provider=spec.profile.provider):
                provider, _ = spec.provider(response=FakeResponse(spec.body()))
                attempt, _ = measure(provider, max_output_tokens=10)
                self.assertEqual(attempt["outcome"], "invalid_response")


class FailureMappingTest(unittest.TestCase):
    """Items 9-12: rate limits, provider errors, transport, timeouts."""

    def outcome(self, spec, **opener_kwargs):
        provider, _ = spec.provider(**opener_kwargs)
        attempt, results = measure(provider)
        self.assertEqual(results, [])
        self.assertIsNone(attempt["input_tokens"])
        return attempt["outcome"]

    def test_http_status_codes(self):
        statuses = {
            429: "rate_limited",
            500: "provider_error",
            503: "provider_error",
            408: "timeout",
            504: "timeout",
        }
        for spec in SPECS:
            for status, category in statuses.items():
                with self.subTest(
                    provider=spec.profile.provider, status=status
                ):
                    self.assertEqual(
                        self.outcome(spec, error=http_error(spec, status)),
                        category,
                    )
        anthropic = BY_PROVIDER["anthropic"]
        self.assertEqual(  # 529 overloaded
            self.outcome(anthropic, error=http_error(anthropic, 529)),
            "provider_error",
        )

    def test_connection_and_timeout_errors(self):
        errors = {
            urllib.error.URLError("dns failure"): "transport_error",
            ConnectionRefusedError(): "transport_error",
            TimeoutError(): "timeout",
            socket.timeout(): "timeout",
        }
        for spec in SPECS:
            for error, category in errors.items():
                with self.subTest(
                    provider=spec.profile.provider, error=type(error).__name__
                ):
                    self.assertEqual(self.outcome(spec, error=error), category)

    def test_failures_while_streaming(self):
        for spec in SPECS:
            for error, category in (
                (TimeoutError(), "timeout"),
                (ConnectionResetError(), "transport_error"),
            ):
                with self.subTest(
                    provider=spec.profile.provider, error=type(error).__name__
                ):
                    response = FakeResponse(
                        spec.body(), fail_on_line=6, error=error
                    )
                    self.assertEqual(
                        self.outcome(spec, response=response), category
                    )

    def test_error_events(self):
        for spec in SPECS:
            for event, category in (
                (spec.rate_limit_event, "rate_limited"),
                (spec.provider_error_event, "provider_error"),
            ):
                with self.subTest(provider=spec.profile.provider, event=event):
                    body = spec.body(final=False) + sse(event)
                    self.assertEqual(
                        self.outcome(spec, response=FakeResponse(body)),
                        category,
                    )

    def test_other_in_stream_failures(self):
        cases = {
            "anthropic": anthropic_error("timeout_error"),
            "google": google_error("deadline_exceeded"),
            "xai": {"type": "response.failed", "response": {"id": "resp_9f2"}},
        }
        expected = {
            "anthropic": "timeout",
            "google": "timeout",
            "xai": "provider_error",
        }
        for provider_name, event in cases.items():
            with self.subTest(provider=provider_name):
                spec = BY_PROVIDER[provider_name]
                body = spec.body(final=False) + sse(event)
                self.assertEqual(
                    self.outcome(spec, response=FakeResponse(body)),
                    expected[provider_name],
                )

    def test_our_own_request_errors_are_not_recorded(self):
        for spec in SPECS:
            for status in (400, 401, 402, 403, 404):
                with self.subTest(
                    provider=spec.profile.provider, status=status
                ):
                    provider, _ = spec.provider(error=http_error(spec, status))
                    with self.assertRaises(spec.module.RequestRejected) as ctx:
                        measure(provider)
                    self.assertIsInstance(
                        ctx.exception, http_streaming.RequestRejected
                    )
                    self.assertEqual(ctx.exception.status, status)

    def test_in_stream_account_errors_are_not_recorded(self):
        for spec in SPECS:
            if spec.rejected_event is None:
                continue
            with self.subTest(provider=spec.profile.provider):
                provider, _ = spec.provider(
                    response=FakeResponse(
                        spec.body(final=False) + sse(spec.rejected_event)
                    )
                )
                with self.assertRaises(http_streaming.RequestRejected):
                    measure(provider)

    def test_rejections_are_not_saved(self):
        spec = BY_PROVIDER["anthropic"]
        provider, _ = spec.provider(error=http_error(spec, 401))
        with tempfile.TemporaryDirectory() as tmp:
            db_path = pathlib.Path(tmp) / "x.db"
            with self.assertRaises(http_streaming.RequestRejected):
                benchmark.run_attempt(
                    provider, WORKLOAD, "prod", db_path, origin=ORIGIN
                )
            self.assertEqual(
                storage.load_recent_requests(db_path, "prod", 5), []
            )

    def test_anthropic_http_failure_keeps_request_id(self):
        spec = BY_PROVIDER["anthropic"]
        error = http_error(spec, 529, headers={"request-id": "req_529"})
        provider, _ = spec.provider(error=error)
        attempt, _ = measure(provider)
        self.assertEqual(
            (attempt["outcome"], attempt["provider_request_id"]),
            ("provider_error", "req_529"),
        )


class SecretHandlingTest(unittest.TestCase):
    """Item 13: secrets, prompts, responses and error text never leak."""

    def test_key_prompt_response_and_error_text_are_not_kept(self):
        for spec in SPECS:
            with self.subTest(provider=spec.profile.provider):
                self.assertNotIn(FAKE_KEY, repr(spec.provider()[0]))
                error_body = json.dumps(
                    {"error": {"type": SECRETISH, "message": SECRETISH}}
                ).encode()
                failed, _ = spec.provider(
                    error=http_error(spec, 500, body=error_body)
                )
                attempt, _ = measure(failed)
                self.assertNotIn(SECRETISH, json.dumps(attempt["diagnostics"]))
                provider, _ = spec.provider(
                    response=FakeResponse(
                        spec.body(texts=("Secret", " answer")),
                        spec.request_id_headers,
                    )
                )
                with tempfile.TemporaryDirectory() as tmp:
                    db_path = pathlib.Path(tmp) / "x.db"
                    request, results, request_id = benchmark.run_attempt(
                        provider, WORKLOAD, "prod", db_path, origin=ORIGIN
                    )
                    out = io.StringIO()
                    with contextlib.redirect_stdout(out):
                        benchmark.print_summary(
                            request, results, request_id, db_path, False
                        )
                    stored = db_path.read_bytes()
                for secret in (
                    FAKE_KEY,
                    WORKLOAD.prompt[:200],
                    "Secret answer",
                ):
                    self.assertNotIn(secret, out.getvalue())
                    self.assertNotIn(secret.encode(), stored)

    def test_empty_key_is_refused(self):
        for spec in SPECS:
            with self.subTest(provider=spec.profile.provider):
                with self.assertRaises(ValueError):
                    spec.adapter("")


class PersistenceTest(unittest.TestCase):
    """Items 19-24: provider facts and cost basis are stored unchanged."""

    def run_one(self, spec, body, db_path):
        provider, _ = spec.provider(
            response=FakeResponse(body, spec.request_id_headers)
        )
        _, _, request_id = benchmark.run_attempt(
            provider, WORKLOAD, "prod", db_path, origin=ORIGIN
        )
        return storage.load_request(db_path, request_id)

    def test_each_provider_record_is_complete_and_auditable(self):
        expected = {
            # (input, output, cached, input rate, output rate, cached rate)
            "anthropic": (1950, 40, 0, 0.10, 0.50, 0.01),
            "google": (2010, 43, 0, 0.30, 2.50, 0.03),
            "xai": (1987, 41, 0, 1.25, 2.50, 0.20),
        }
        with tempfile.TemporaryDirectory() as tmp:
            db_path = pathlib.Path(tmp) / "x.db"
            for spec in SPECS:
                with self.subTest(provider=spec.profile.provider):
                    stored = self.run_one(spec, spec.body(), db_path)
                    tokens_in, tokens_out, cached, rate_in, rate_out, rate_c = (
                        expected[spec.profile.provider]
                    )
                    self.assertEqual(
                        (
                            stored["provider"],
                            stored["model"],
                            stored["request_profile_id"],
                            stored["workload_id"],
                            stored["cache_policy"],
                            stored["provider_request_id"],
                        ),
                        (
                            spec.profile.provider,
                            spec.profile.model,
                            spec.profile.profile_id,
                            "interactive-chat-v1",
                            spec.profile.cache_policy,
                            spec.request_id,
                        ),
                    )
                    self.assertEqual(
                        (
                            stored["input_tokens"],
                            stored["output_tokens"],
                            stored["cached_input_tokens"],
                            stored["requested_max_output_tokens"],
                        ),
                        (tokens_in, tokens_out, cached, 300),
                    )
                    self.assertEqual(
                        (
                            stored["input_price_per_1m"],
                            stored["output_price_per_1m"],
                            stored["cached_input_price_per_1m"],
                        ),
                        (rate_in, rate_out, rate_c),
                    )
                    self.assertAlmostEqual(
                        stored["total_cost"],
                        (tokens_in * rate_in + tokens_out * rate_out) / 1e6,
                        places=15,
                    )
            # Same workload text, different provider token counts: all kept.
            self.assertEqual(
                {
                    r["input_tokens"]
                    for r in storage.load_recent_requests(db_path, "prod", 10)
                },
                {1950, 2010, 1987},
            )

    def test_reported_cached_tokens_are_charged_at_the_cached_rate(self):
        spec = BY_PROVIDER["xai"]
        with tempfile.TemporaryDirectory() as tmp:
            stored = self.run_one(
                spec,
                xai_body(input_tokens=2000, cached=1500, output_tokens=40),
                pathlib.Path(tmp) / "x.db",
            )
        self.assertEqual(stored["cached_input_tokens"], 1500)
        self.assertAlmostEqual(
            stored["input_cost"], (500 * 1.25 + 1500 * 0.20) / 1e6, places=15
        )

    def test_failed_attempt_cost_and_tokens_are_unknown(self):
        spec = BY_PROVIDER["google"]
        provider, _ = spec.provider(error=http_error(spec, 503))
        with tempfile.TemporaryDirectory() as tmp:
            db_path = pathlib.Path(tmp) / "x.db"
            _, _, request_id = benchmark.run_attempt(
                provider, WORKLOAD, "prod", db_path, origin=ORIGIN
            )
            stored = storage.load_request(db_path, request_id)
        for column in ("input_tokens", "output_tokens", "total_cost"):
            self.assertIsNone(stored[column])
        self.assertEqual(
            stored["request_profile_id"], targets.GOOGLE.profile_id
        )
        self.assertEqual(stored["input_price_per_1m"], 0.30)


if __name__ == "__main__":
    unittest.main()
