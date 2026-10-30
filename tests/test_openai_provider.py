"""Tests for the OpenAI adapter and the real smoke command.

No test here touches the network: every request goes through a fake opener,
and socket use is blocked where a code path must stay offline. No test spends
money.

`storage.load_request` returns None only for an unknown id; tests look up ids
they have just saved, so its result is subscripted directly.
"""

# pylint: disable=unsubscriptable-object

import contextlib
import io
import json
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import urllib.error
import urllib.request

from llm_metrics import __main__ as cli
from llm_metrics import benchmark
from llm_metrics import latency
from llm_metrics import openai_provider
from llm_metrics import pricing
from llm_metrics import providers
from llm_metrics import real_smoke
from llm_metrics import storage

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SMOKE_CASE = {
    "workload_id": "smoke.short_text.v2",
    "origin": ("local", "unknown"),
}
FAKE_KEY = "fake-test-key-NEVER-SHOW-THIS-0123456789"


def sse(*events):
    """Server-sent-event bytes for the given event dicts (or raw strings)."""
    out = []
    for event in events:
        payload = event if isinstance(event, str) else json.dumps(event)
        out.append(f"event: x\ndata: {payload}\n\n")
    return "".join(out).encode("utf-8")


def delta(text):
    return {"type": "response.output_text.delta", "delta": text}


def completed(input_tokens=12, output_tokens=3):
    return {
        "type": "response.completed",
        "response": {
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            }
        },
    }


class FakeResponse(io.BytesIO):
    """Readable like an HTTP response; optionally fails on the nth readline."""

    def __init__(self, body, fail_on_line=None, error=None):
        super().__init__(body)
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


def provider_with(**kwargs):
    opener = FakeOpener(**kwargs)
    return openai_provider.OpenAIProvider(FAKE_KEY, opener=opener), opener


def http_error(status):
    return urllib.error.HTTPError(
        openai_provider.API_URL, status, "error", {}, io.BytesIO(b"{}")
    )


class StreamTranslationTest(unittest.TestCase):

    def test_success_yields_text_chunks_then_authoritative_usage(self):
        provider, _ = provider_with(
            response=FakeResponse(
                sse(
                    {"type": "response.created"},
                    delta("Hel"),
                    delta("lo"),
                    {"type": "response.output_text.done"},
                    completed(12, 3),
                )
            )
        )
        self.assertEqual(
            list(provider.stream("hi", 64)),
            ["Hel", "lo", providers.Usage(12, 3)],
        )

    def test_measurement_uses_provider_usage_not_chunks(self):
        provider, _ = provider_with(
            response=FakeResponse(
                sse(delta("Hel"), delta("lo"), completed(12, 5))
            )
        )
        attempt, results = latency.measure_request(provider, "hi", 64)
        self.assertEqual(attempt["outcome"], "success")
        self.assertEqual(
            (attempt["input_tokens"], attempt["output_tokens"]), (12, 5)
        )  # 2 chunks
        self.assertEqual(
            {r["metric"] for r in results},
            {
                "total_latency",
                "ttft",
                "output_tokens_per_s",
                "output_chunks_per_s",
            },
        )
        self.assertEqual(attempt["provider"], "openai")
        self.assertEqual(attempt["model"], "gpt-6-luna")

    def test_request_is_one_small_capped_streaming_call(self):
        provider, opener = provider_with(
            response=FakeResponse(sse(delta("a"), completed()))
        )
        list(provider.stream("the prompt", 64))
        self.assertEqual(len(opener.calls), 1)  # Exactly one HTTP request.
        request, timeout = opener.calls[0]
        self.assertEqual(request.full_url, openai_provider.API_URL)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(timeout, openai_provider.TIMEOUT_S)
        body = json.loads(request.data)
        self.assertEqual(
            body,
            {
                "model": "gpt-6-luna",
                "input": "the prompt",
                "max_output_tokens": 64,
                "stream": True,
                "store": False,
                "reasoning": {"effort": "none"},
                # Explicit cache mode without breakpoints: no prompt caching.
                "prompt_cache_options": {"mode": "explicit"},
            },
        )
        self.assertNotIn("prompt_cache_breakpoint", request.data.decode())
        self.assertEqual(
            openai_provider.OpenAIProvider.cache_policy, "disabled"
        )
        self.assertNotIn("tools", body)
        self.assertEqual(
            request.get_header("Authorization"), f"Bearer {FAKE_KEY}"
        )

    def test_cap_reached_is_still_a_completed_response_with_usage(self):
        incomplete = {
            "type": "response.incomplete",
            "response": {
                "incomplete_details": {"reason": "max_output_tokens"},
                "usage": {"input_tokens": 12, "output_tokens": 64},
            },
        }
        provider, _ = provider_with(
            response=FakeResponse(sse(delta("a"), delta("b"), incomplete))
        )
        attempt, _ = latency.measure_request(provider, "hi", 64)
        self.assertEqual(
            (attempt["outcome"], attempt["output_tokens"]), ("success", 64)
        )


class ProviderRequestIdTest(unittest.TestCase):
    """OpenAI's x-request-id is stored beside our own id, never instead."""

    def response(self, body, request_id="req_8d31bcc50b4b40b58ae702b1305f67de"):
        response = FakeResponse(body)
        response.headers = {"x-request-id": request_id}
        response.status = 200
        return response

    def test_success_carries_and_stores_the_provider_request_id(self):
        provider, _ = provider_with(
            response=self.response(sse(delta("a"), completed()))
        )
        with tempfile.TemporaryDirectory() as tmp:
            db_path = pathlib.Path(tmp) / "x.db"
            _, _, request_id = benchmark.run_attempt(
                provider, "p", 64, "prod", db_path, **SMOKE_CASE
            )
            stored = storage.load_request(db_path, request_id)
        self.assertEqual(
            stored["provider_request_id"],
            "req_8d31bcc50b4b40b58ae702b1305f67de",
        )
        self.assertNotEqual(
            request_id, stored["provider_request_id"]
        )  # our own UUID stays the id
        self.assertEqual(len(request_id), 32)

    def test_failures_carry_the_provider_request_id(self):
        cases = {
            "error_event": self.response(
                sse({"type": "error", "error": {"code": "server_error"}})
            ),
            "response_failed": self.response(
                sse({"type": "response.failed", "response": {}})
            ),
            "invalid_usage": self.response(
                sse(delta("a"), {"type": "response.completed", "response": {}})
            ),
            # Detected by measurement, not the provider: no id (a known
            # limitation).
            "stream_ended_without_final_event": self.response(sse(delta("a"))),
        }
        for name, response in cases.items():
            with self.subTest(case=name):
                attempt, _ = latency.measure_request(
                    provider_with(response=response)[0], "p", 64
                )
                self.assertNotEqual(attempt["outcome"], "success")
                expected = (
                    None
                    if name.startswith("stream_ended")
                    else "req_8d31bcc50b4b40b58ae702b1305f67de"
                )
                self.assertEqual(attempt["provider_request_id"], expected)

    def test_http_5xx_carries_the_provider_request_id(self):
        error = urllib.error.HTTPError(
            openai_provider.API_URL,
            503,
            "x",
            {"x-request-id": "req_5xx"},
            io.BytesIO(b"{}"),
        )
        attempt, _ = latency.measure_request(
            provider_with(error=error)[0], "p", 64
        )
        self.assertEqual(
            (attempt["outcome"], attempt["provider_request_id"]),
            ("provider_error", "req_5xx"),
        )

    def test_unsafe_or_missing_ids_are_not_stored(self):
        for header in (SECRETISH, "x" * 101, None):
            with self.subTest(header=header):
                response = FakeResponse(sse(delta("a"), completed()))
                response.headers = (
                    {} if header is None else {"x-request-id": header}
                )
                attempt, _ = latency.measure_request(
                    provider_with(response=response)[0], "p", 64
                )
                self.assertIsNone(attempt["provider_request_id"])

    def test_connection_failure_has_no_provider_request_id(self):
        attempt, _ = latency.measure_request(
            provider_with(error=ConnectionRefusedError())[0], "p", 64
        )
        self.assertEqual(attempt["outcome"], "transport_error")
        self.assertIsNone(attempt["provider_request_id"])


class UsageIsNeverFabricatedTest(unittest.TestCase):

    def outcome(self, body):
        provider, _ = provider_with(response=FakeResponse(body))
        attempt, results = latency.measure_request(provider, "hi", 64)
        return attempt, results

    def test_missing_or_invalid_usage_is_invalid_response(self):
        bodies = {
            "no final event": sse(delta("a"), delta("b")),
            "final event without usage": sse(
                delta("a"), {"type": "response.completed", "response": {}}
            ),
            "usage missing a count": sse(
                delta("a"),
                {
                    "type": "response.completed",
                    "response": {"usage": {"input_tokens": 3}},
                },
            ),
            "negative count": sse(delta("a"), completed(3, -1)),
            "non-integer count": sse(delta("a"), completed("3", 1)),
            "boolean count": sse(delta("a"), completed(True, 1)),
            "not JSON": sse(delta("a"), "{not json"),
            "delta not text": sse(
                {"type": "response.output_text.delta", "delta": 5}
            ),
        }
        for name, body in bodies.items():
            with self.subTest(name):
                attempt, results = self.outcome(body)
                self.assertEqual(attempt["outcome"], "invalid_response")
                self.assertIsNone(attempt["input_tokens"])
                self.assertIsNone(attempt["output_tokens"])
                self.assertEqual(results, [])


def completed_with_details(details, input_tokens=12, output_tokens=3):
    usage = {"input_tokens": input_tokens, "output_tokens": output_tokens}
    if details is not None:
        usage["input_tokens_details"] = details
    return {"type": "response.completed", "response": {"usage": usage}}


class CachedInputTokensTest(unittest.TestCase):
    """cached_input_tokens comes only from OpenAI usage, never inferred.

    The source field is usage.input_tokens_details.cached_tokens.
    """

    def attempt(self, details, input_tokens=12):
        provider, _ = provider_with(
            response=FakeResponse(
                sse(
                    delta("a"),
                    delta("b"),
                    completed_with_details(details, input_tokens),
                )
            )
        )
        attempt, _ = latency.measure_request(provider, "hi", 64)
        return attempt

    def test_reported_values_are_carried_and_zero_is_kept(self):
        for details, expected in (
            ({"cached_tokens": 0}, 0),
            ({"cached_tokens": 8}, 8),
            ({"cached_tokens": 12}, 12),
        ):
            with self.subTest(details=details):
                attempt = self.attempt(details)
                self.assertEqual(attempt["outcome"], "success")
                self.assertEqual(attempt["cached_input_tokens"], expected)

    def test_not_reported_is_unknown_never_zero(self):
        for details in (None, {}, {"cached_tokens": None}, "not a dict"):
            with self.subTest(details=details):
                attempt = self.attempt(details)
                self.assertEqual(attempt["outcome"], "success")
                self.assertIsNone(attempt["cached_input_tokens"])

    def test_malformed_cached_tokens_are_invalid_response(self):
        for cached in (-1, "3", True, 1.5, 13):  # 13 > input_tokens (12)
            with self.subTest(cached=cached):
                attempt = self.attempt({"cached_tokens": cached})
                self.assertEqual(attempt["outcome"], "invalid_response")
                self.assertIsNone(attempt["cached_input_tokens"])

    def test_cached_tokens_are_stored_and_zero_differs_from_null(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = pathlib.Path(tmp) / "x.db"
            stored = {}
            for name, details in (
                ("zero", {"cached_tokens": 0}),
                ("missing", None),
                ("some", {"cached_tokens": 5}),
            ):
                provider, _ = provider_with(
                    response=FakeResponse(
                        sse(
                            delta("a"),
                            delta("b"),
                            completed_with_details(details),
                        )
                    )
                )
                _, _, request_id = benchmark.run_attempt(
                    provider, "p", 64, "prod", db_path, **SMOKE_CASE
                )
                stored[name] = storage.load_request(db_path, request_id)
        self.assertEqual(stored["zero"]["cached_input_tokens"], 0)
        self.assertIsNone(stored["missing"]["cached_input_tokens"])
        self.assertEqual(stored["some"]["cached_input_tokens"], 5)
        for request in stored.values():
            self.assertEqual(request["cache_policy"], "disabled")

    def test_new_attempts_never_record_an_unknown_or_invented_policy(self):
        for policy in ("unknown", "cold", ""):
            with self.subTest(policy=policy):
                provider = providers.DummyProvider(
                    first_token_delay_s=0, inter_token_delay_s=0
                )
                provider.cache_policy = policy
                with tempfile.TemporaryDirectory() as tmp:
                    with self.assertRaises(ValueError):
                        benchmark.run_attempt(
                            provider,
                            "p",
                            64,
                            "test",
                            pathlib.Path(tmp) / "x.db",
                            **SMOKE_CASE,
                        )
                    self.assertFalse((pathlib.Path(tmp) / "x.db").exists())

    def test_failed_attempt_has_unknown_cached_tokens(self):
        provider, _ = provider_with(
            response=FakeResponse(
                sse({"type": "error", "error": {"code": "server_error"}})
            )
        )
        attempt, _ = latency.measure_request(provider, "hi", 64)
        self.assertEqual(attempt["outcome"], "provider_error")
        self.assertIsNone(attempt["cached_input_tokens"])


class FailureMappingTest(unittest.TestCase):

    def outcome(self, **kwargs):
        provider, _ = provider_with(**kwargs)
        attempt, results = latency.measure_request(provider, "hi", 64)
        self.assertEqual(results, [])
        return attempt["outcome"]

    def test_http_status_codes(self):
        for status, category in [
            (429, "rate_limited"),
            (500, "provider_error"),
            (502, "provider_error"),
            (503, "provider_error"),
            (408, "timeout"),
            (504, "timeout"),
        ]:
            with self.subTest(status=status):
                self.assertEqual(
                    self.outcome(error=http_error(status)), category
                )

    def test_connection_and_timeout_errors(self):
        cases = [
            (urllib.error.URLError("dns failure"), "transport_error"),
            (ConnectionRefusedError(), "transport_error"),
            (TimeoutError(), "timeout"),
            (socket.timeout(), "timeout"),
        ]
        for error, category in cases:
            with self.subTest(error=type(error).__name__):
                self.assertEqual(self.outcome(error=error), category)

    def test_failures_while_streaming(self):
        body = sse(delta("a"), delta("b"), completed())
        for error, category in [
            (TimeoutError(), "timeout"),
            (ConnectionResetError(), "transport_error"),
        ]:
            with self.subTest(error=type(error).__name__):
                response = FakeResponse(body, fail_on_line=4, error=error)
                self.assertEqual(self.outcome(response=response), category)

    def test_error_events(self):
        cases = [
            ({"type": "response.failed", "response": {}}, "provider_error"),
            ({"type": "error", "code": "rate_limit_exceeded"}, "rate_limited"),
            ({"type": "error", "code": "server_error"}, "provider_error"),
            (
                {
                    "type": "response.incomplete",
                    "response": {
                        "incomplete_details": {"reason": "content_filter"}
                    },
                },
                "provider_error",
            ),
        ]
        for event, category in cases:
            with self.subTest(event=event):
                self.assertEqual(
                    self.outcome(response=FakeResponse(sse(delta("a"), event))),
                    category,
                )

    def test_our_own_request_errors_are_not_provider_failures(self):
        for status in (400, 401, 403, 404):
            with self.subTest(status=status):
                provider, _ = provider_with(error=http_error(status))
                with self.assertRaises(openai_provider.RequestRejected):
                    latency.measure_request(provider, "hi", 64)

    def test_account_quota_errors_are_not_provider_failures(self):
        quota_body = json.dumps(
            {
                "error": {
                    "code": "insufficient_quota",
                    "type": "insufficient_quota",
                }
            }
        ).encode()
        cases = {
            "http_429": dict(
                error=urllib.error.HTTPError(
                    openai_provider.API_URL,
                    429,
                    "x",
                    {},
                    io.BytesIO(quota_body),
                )
            ),
            "nested_event": dict(
                response=FakeResponse(
                    sse(
                        {
                            "type": "error",
                            "error": {
                                "code": "credit_balance_exhausted",
                                "type": "insufficient_quota",
                            },
                        }
                    )
                )
            ),
            "flat_event": dict(
                response=FakeResponse(
                    sse({"type": "error", "code": "insufficient_quota"})
                )
            ),
            "response_failed": dict(
                response=FakeResponse(
                    sse(
                        {
                            "type": "response.failed",
                            "response": {
                                "status": "failed",
                                "error": {"code": "insufficient_quota"},
                            },
                        }
                    )
                )
            ),
        }
        for name, kwargs in cases.items():
            with self.subTest(case=name):
                provider, _ = provider_with(**kwargs)
                with self.assertRaises(openai_provider.RequestRejected) as ctx:
                    latency.measure_request(provider, "hi", 64)
                self.assertIn(
                    ctx.exception.diagnostics["error_code"],
                    ("insufficient_quota", "credit_balance_exhausted"),
                )

    def test_quota_rejection_is_not_recorded(self):
        event = {
            "type": "error",
            "error": {
                "code": "credit_balance_exhausted",
                "type": "insufficient_quota",
            },
        }
        provider, _ = provider_with(response=FakeResponse(sse(event)))
        with tempfile.TemporaryDirectory() as tmp:
            db_path = pathlib.Path(tmp) / "x.db"
            with self.assertRaises(openai_provider.RequestRejected):
                benchmark.run_attempt(
                    provider, "p", 64, "prod", db_path, **SMOKE_CASE
                )
            self.assertFalse(
                db_path.exists()
                and b"credit_balance_exhausted" in db_path.read_bytes()
            )

    def test_plain_rate_limit_429_is_still_rate_limited(self):
        body = json.dumps(
            {"error": {"code": "rate_limit_exceeded", "type": "requests"}}
        ).encode()
        error = urllib.error.HTTPError(
            openai_provider.API_URL, 429, "x", {}, io.BytesIO(body)
        )
        self.assertEqual(self.outcome(error=error), "rate_limited")

    def test_programming_errors_are_not_mislabelled(self):
        provider, _ = provider_with(error=KeyError("bug"))
        with self.assertRaises(KeyError):
            latency.measure_request(provider, "hi", 64)


SECRETISH = (
    f"Bearer {FAKE_KEY} prompt text: the prompt; response text: Hello there"
)


class DiagnosticsTest(unittest.TestCase):
    """Every failure path reports where it failed, with sanitized ids only."""

    def failed(self, **kwargs):
        provider, _ = provider_with(**kwargs)
        attempt, _ = latency.measure_request(provider, "the prompt", 64)
        return attempt

    def assert_no_free_text(self, diagnostics):
        flat = json.dumps(diagnostics)
        for secret in (
            FAKE_KEY,
            "Bearer",
            "the prompt",
            "Hello there",
            "message",
        ):
            self.assertNotIn(secret, flat)

    def test_http_5xx_reports_status_request_id_and_error_code(self):
        body = json.dumps(
            {
                "error": {
                    "code": "server_error",
                    "type": "server_error",
                    "param": None,
                    "message": SECRETISH,
                }
            }
        ).encode()
        error = urllib.error.HTTPError(
            openai_provider.API_URL,
            503,
            "x",
            {"x-request-id": "req_abc123"},
            io.BytesIO(body),
        )
        attempt = self.failed(error=error)
        self.assertEqual(attempt["outcome"], "provider_error")
        self.assertEqual(
            attempt["diagnostics"],
            {
                "where": "http_status",
                "http_status": "503",
                "request_id": "req_abc123",
                "error_code": "server_error",
                "error_type": "server_error",
                "error_param": "<none>",
            },
        )
        self.assert_no_free_text(attempt["diagnostics"])

    def test_response_failed_event(self):
        event = {
            "type": "response.failed",
            "response": {
                "status": "failed",
                "error": {"code": "server_error", "message": SECRETISH},
            },
        }
        response = FakeResponse(sse(delta("Hello there"), event))
        response.headers = {"x-request-id": "req_42"}
        response.status = 200
        attempt = self.failed(response=response)
        self.assertEqual(attempt["outcome"], "provider_error")
        self.assertEqual(
            attempt["diagnostics"],
            {
                "where": "event:response.failed",
                "http_status": "200",
                "request_id": "req_42",
                "response_status": "failed",
                "error_code": "server_error",
            },
        )
        self.assert_no_free_text(attempt["diagnostics"])

    def test_error_event_reports_code_type_param(self):
        event = {
            "type": "error",
            "code": "invalid_value",
            "type_": "x",
            "param": "reasoning.effort",
            "message": SECRETISH,
        }
        attempt = self.failed(response=FakeResponse(sse(event)))
        self.assertEqual(attempt["outcome"], "provider_error")
        self.assertEqual(attempt["diagnostics"]["where"], "event:error")
        self.assertEqual(attempt["diagnostics"]["error_code"], "invalid_value")
        self.assertEqual(
            attempt["diagnostics"]["error_param"], "reasoning.effort"
        )
        self.assert_no_free_text(attempt["diagnostics"])

    def test_nested_error_event_details_are_reported(self):
        # Shape seen live: HTTP 200, then {"type": "error", "error": {...}}.
        event = {
            "type": "error",
            "sequence_number": 1,
            "error": {
                "type": "invalid_request_error",
                "code": "unsupported_value",
                "param": "reasoning.effort",
                "message": SECRETISH,
            },
        }
        response = FakeResponse(sse(event))
        response.headers = {
            "x-request-id": "req_e7b69a029b404d379527b117fff3212e"
        }
        response.status = 200
        attempt = self.failed(response=response)
        self.assertEqual(attempt["outcome"], "provider_error")
        self.assertEqual(
            attempt["diagnostics"],
            {
                "where": "event:error",
                "http_status": "200",
                "request_id": "req_e7b69a029b404d379527b117fff3212e",
                "error_code": "unsupported_value",
                "error_type": "invalid_request_error",
                "error_param": "reasoning.effort",
            },
        )
        self.assert_no_free_text(attempt["diagnostics"])

    def test_event_type_is_not_reported_as_error_type(self):
        attempt = self.failed(
            response=FakeResponse(
                sse({"type": "error", "code": "server_error"})
            )
        )
        self.assertNotIn("error_type", attempt["diagnostics"])
        self.assertEqual(attempt["diagnostics"]["error_code"], "server_error")

    def test_nested_rate_limit_code_maps_to_rate_limited(self):
        event = {
            "type": "error",
            "error": {"code": "rate_limit_exceeded", "type": "requests"},
        }
        self.assertEqual(
            self.failed(response=FakeResponse(sse(event)))["outcome"],
            "rate_limited",
        )

    def test_incomplete_reason_is_reported(self):
        event = {
            "type": "response.incomplete",
            "response": {"incomplete_details": {"reason": "content_filter"}},
        }
        attempt = self.failed(response=FakeResponse(sse(delta("a"), event)))
        self.assertEqual(attempt["outcome"], "provider_error")
        self.assertEqual(
            attempt["diagnostics"]["where"], "event:response.incomplete"
        )
        self.assertEqual(
            attempt["diagnostics"]["incomplete_reason"], "content_filter"
        )

    def test_free_text_values_are_redacted(self):
        event = {
            "type": "error",
            "code": SECRETISH,
            "param": "has spaces in it",
        }
        attempt = self.failed(response=FakeResponse(sse(event)))
        self.assertEqual(attempt["diagnostics"]["error_code"], "<redacted>")
        self.assertEqual(attempt["diagnostics"]["error_param"], "<redacted>")
        self.assert_no_free_text(attempt["diagnostics"])

    def test_rejected_request_reports_param(self):
        body = json.dumps(
            {
                "error": {
                    "code": "unsupported_parameter",
                    "type": "invalid_request_error",
                    "param": "reasoning.effort",
                    "message": SECRETISH,
                }
            }
        ).encode()
        provider, _ = provider_with(
            error=urllib.error.HTTPError(
                openai_provider.API_URL, 400, "x", {}, io.BytesIO(body)
            )
        )
        with self.assertRaises(openai_provider.RequestRejected) as ctx:
            latency.measure_request(provider, "the prompt", 64)
        self.assertEqual(
            ctx.exception.diagnostics["error_param"], "reasoning.effort"
        )
        self.assertEqual(
            ctx.exception.diagnostics["error_code"], "unsupported_parameter"
        )
        self.assert_no_free_text(ctx.exception.diagnostics)

    def test_diagnostics_are_never_stored(self):
        event = {"type": "error", "code": "server_error_marker_xyz"}
        provider, _ = provider_with(response=FakeResponse(sse(event)))
        with tempfile.TemporaryDirectory() as tmp:
            db_path = pathlib.Path(tmp) / "x.db"
            request, _, _ = benchmark.run_attempt(
                provider, "p", 64, "prod", db_path, **SMOKE_CASE
            )
            self.assertEqual(
                request["diagnostics"]["error_code"], "server_error_marker_xyz"
            )
            self.assertNotIn(b"server_error_marker_xyz", db_path.read_bytes())


class SecretHandlingTest(unittest.TestCase):

    def test_key_is_not_shown_or_stored(self):
        provider, _ = provider_with(
            response=FakeResponse(
                sse(delta("Hello"), delta(" there"), completed())
            )
        )
        self.assertNotIn(FAKE_KEY, repr(provider))
        self.assertNotIn(FAKE_KEY, str(openai_provider.RequestRejected(401)))
        self.assertNotIn(FAKE_KEY, str(providers.ProviderFailure("timeout")))
        with tempfile.TemporaryDirectory() as tmp:
            db_path = pathlib.Path(tmp) / "x.db"
            request, results, request_id = benchmark.run_attempt(
                provider, "secret prompt", 64, "prod", db_path, **SMOKE_CASE
            )
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                benchmark.print_summary(
                    request, results, request_id, db_path, simulated=False
                )
            stored = db_path.read_bytes()
        printed = out.getvalue()
        for secret in (FAKE_KEY, "secret prompt", "Hello there"):
            self.assertNotIn(secret, printed)
            self.assertNotIn(secret.encode(), stored)
        self.assertIn("Outcome: success", printed)

    def test_empty_key_is_refused(self):
        with self.assertRaises(ValueError):
            openai_provider.OpenAIProvider("")


class PricingTest(unittest.TestCase):

    def test_openai_price_and_cost(self):
        price = pricing.price_for("openai", "gpt-6-luna")
        self.assertEqual(
            price, pricing.Price(input_per_1m=0.10, output_per_1m=0.50)
        )
        cost = pricing.request_cost(
            20, 15, price
        )  # 20 * 0.10 / 1e6 + 15 * 0.50 / 1e6
        self.assertAlmostEqual(cost["input_cost"], 0.000002, places=15)
        self.assertAlmostEqual(cost["output_cost"], 0.0000075, places=15)
        self.assertAlmostEqual(cost["total_cost"], 0.0000095, places=15)

    def test_price_provenance_is_recorded_and_verified(self):
        source, verified_on = pricing.PRICE_PROVENANCE[("openai", "gpt-6-luna")]
        self.assertTrue(
            source.startswith("https://developers.openai.com/api/docs/pricing")
        )
        self.assertIsNotNone(verified_on)
        self.assertEqual(verified_on, "2026-10-30")


def no_network(test):
    """Decorator: any attempt to open a socket or URL fails the test."""

    def blocked(*args, **kwargs):
        raise AssertionError("network access attempted")

    test = mock.patch("socket.socket.connect", blocked)(test)
    test = mock.patch("urllib.request.urlopen", blocked)(test)
    return test


class RealSmokeCommandTest(unittest.TestCase):
    argv = []

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db_path = pathlib.Path(tmp.name) / "x.db"

    def run_main(self, env, opener=None):
        out, err = io.StringIO(), io.StringIO()
        patches = [
            mock.patch.dict(
                os.environ,
                {
                    "LLM_METRICS_DB_PATH": str(self.db_path),
                    "LLM_METRICS_ORIGIN_CLOUD": "",
                    "LLM_METRICS_ORIGIN_REGION": "",
                    **env,
                },
            )
        ]
        if opener is not None:
            real_init = openai_provider.OpenAIProvider.__init__

            # Same signature as the real __init__; the caller's opener is
            # replaced by the test's fake so no request reaches the network.
            def init(provider, api_key, model="gpt-6-luna", unused_opener=None):
                real_init(provider, api_key, model=model, opener=opener)

            patches.append(
                mock.patch.object(
                    openai_provider.OpenAIProvider, "__init__", init
                )
            )
        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            stack.enter_context(contextlib.redirect_stdout(out))
            stack.enter_context(contextlib.redirect_stderr(err))
            code = real_smoke.main(self.argv)
        return code, out.getvalue(), err.getvalue()

    def only_real_request(self):
        """Returns the only saved real attempt; fails unless there is one."""
        requests = storage.load_recent_requests(self.db_path, "prod", 20)
        self.assertEqual(len(requests), 1)
        return requests[0]

    @no_network
    def test_refuses_without_credentials_and_makes_no_request(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENAI_API_KEY", None)
            code, _, err = self.run_main({})
        self.assertEqual(code, 2)
        self.assertIn("OPENAI_API_KEY is not set. No request was made.", err)
        self.assertFalse(self.db_path.exists())

    def test_refuses_without_credentials_as_a_process(self):
        env = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
        env["LLM_METRICS_DB_PATH"] = str(self.db_path)
        proc = subprocess.run(
            [sys.executable, "-m", "llm_metrics.real_smoke"],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("No request was made", proc.stderr)
        self.assertFalse(self.db_path.exists())

    def test_one_call_recorded_as_real_data_with_summary(self):
        opener = FakeOpener(
            response=FakeResponse(
                sse(delta("Hi"), delta(" there"), completed(20, 15))
            )
        )
        code, out, _ = self.run_main({"OPENAI_API_KEY": FAKE_KEY}, opener)
        self.assertEqual(code, 0)
        self.assertEqual(len(opener.calls), 1)
        self.assertIn(
            "exactly ONE paid API request: provider openai, model gpt-6-luna, "
            "max output tokens 64",
            out,
        )
        self.assertNotIn("not yet verified", out)
        for line in (
            "Outcome: success",
            "Input tokens: 20",
            "Output tokens: 15 of max 64",
            "Cost: $0.000010 (input $0.000002 + output $0.000008)",
            "Rates: $0.10 input / $0.50 output per 1M tokens",
        ):
            self.assertIn(line, out)
        self.assertNotIn("(simulated)", out)
        self.assertNotIn(
            "Provider request id", out
        )  # the fake response sent none
        self.assertNotIn(FAKE_KEY, out)
        self.assertNotIn(real_smoke.PROMPT, out)
        stored = self.only_real_request()
        self.assertEqual(
            (stored["provider"], stored["model"], stored["environment"]),
            ("openai", "gpt-6-luna", "prod"),
        )
        self.assertEqual(
            (
                stored["workload_id"],
                stored["origin_cloud"],
                stored["origin_region"],
            ),
            ("smoke.short_text.v2", "local", "unknown"),
        )
        self.assertIn("Workload: smoke.short_text.v2", out)
        self.assertIn("Cache policy: disabled", out)
        self.assertIn(
            "Cached input tokens: not reported", out
        )  # the fake usage has no details
        self.assertEqual(stored["cache_policy"], "disabled")
        self.assertIsNone(stored["cached_input_tokens"])
        # Real token throughput comes from OpenAI's usage (15 tokens), not the 2
        # chunks.
        self.assertIn("output_tokens_per_s", stored["metrics"])
        self.assertIn("Output token throughput:", out)
        self.assertAlmostEqual(stored["total_cost"], 0.0000095, places=15)
        self.assertEqual(
            storage.load_recent_requests(self.db_path, "test", 20), []
        )

    def test_debug_flag_prints_sanitized_diagnostics_only_when_asked(self):
        event = {
            "type": "response.failed",
            "response": {
                "error": {"code": "server_error", "message": SECRETISH}
            },
        }
        for argv, shown in (([], False), (["--debug"], True)):
            with self.subTest(argv=argv):
                self.argv = argv
                opener = FakeOpener(
                    response=FakeResponse(sse(delta("Hello there"), event))
                )
                code, out, err = self.run_main(
                    {"OPENAI_API_KEY": FAKE_KEY}, opener
                )
                self.assertEqual(code, 0)
                self.assertIn(
                    "Outcome: FAILED — Provider/server error (provider_error)",
                    out,
                )
                self.assertEqual("where=event:response.failed" in err, shown)
                self.assertEqual("error_code=server_error" in err, shown)
                for secret in (
                    FAKE_KEY,
                    "Bearer",
                    real_smoke.PROMPT,
                    "Hello there",
                    "message",
                ):
                    self.assertNotIn(secret, out + err)

    def test_summary_shows_the_provider_request_id(self):
        response = FakeResponse(
            sse(delta("Hi"), delta(" there"), completed(20, 15))
        )
        response.headers = {"x-request-id": "req_42"}
        code, out, _ = self.run_main(
            {"OPENAI_API_KEY": FAKE_KEY}, FakeOpener(response=response)
        )
        self.assertEqual(code, 0)
        self.assertIn("Provider request id: req_42", out)
        stored = self.only_real_request()
        self.assertEqual(stored["provider_request_id"], "req_42")

    def test_origin_comes_from_the_environment(self):
        opener = FakeOpener(
            response=FakeResponse(sse(delta("a"), delta("b"), completed()))
        )
        code, out, _ = self.run_main(
            {
                "OPENAI_API_KEY": FAKE_KEY,
                "LLM_METRICS_ORIGIN_CLOUD": "gcp",
                "LLM_METRICS_ORIGIN_REGION": "us-central1",
            },
            opener,
        )
        self.assertEqual(code, 0)
        self.assertIn("Origin: gcp / us-central1", out)
        stored = self.only_real_request()
        self.assertEqual(
            (stored["origin_cloud"], stored["origin_region"]),
            ("gcp", "us-central1"),
        )

    def test_invalid_origin_is_refused_before_any_request(self):
        opener = FakeOpener(response=FakeResponse(sse(delta("a"), completed())))
        code, _, err = self.run_main(
            {"OPENAI_API_KEY": FAKE_KEY, "LLM_METRICS_ORIGIN_CLOUD": "AWS!"},
            opener,
        )
        self.assertEqual(code, 2)
        self.assertIn("Invalid LLM_METRICS_ORIGIN_CLOUD", err)
        self.assertIn("No request was made", err)
        self.assertEqual(opener.calls, [])
        self.assertFalse(self.db_path.exists())

    def test_unknown_arguments_are_refused_before_any_request(self):
        self.argv = ["--loop"]
        opener = FakeOpener(response=FakeResponse(sse(delta("a"), completed())))
        code, _, err = self.run_main({"OPENAI_API_KEY": FAKE_KEY}, opener)
        self.assertEqual(code, 2)
        self.assertIn("Usage", err)
        self.assertEqual(opener.calls, [])

    def test_rejected_request_is_not_recorded(self):
        opener = FakeOpener(error=http_error(401))
        code, _, err = self.run_main({"OPENAI_API_KEY": FAKE_KEY}, opener)
        self.assertEqual(code, 2)
        self.assertIn("HTTP 401", err)
        self.assertIn("Nothing was recorded", err)
        self.assertNotIn(FAKE_KEY, err)
        self.assertEqual(
            storage.load_recent_requests(self.db_path, "prod", 20), []
        )


class SimulatedPathsStayOfflineTest(unittest.TestCase):

    @no_network
    def test_simulated_cli_makes_no_network_calls(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            os.environ,
            {
                "LLM_METRICS_DB_PATH": str(pathlib.Path(tmp) / "x.db"),
                "APP_ENV": "test",
            },
        ), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(), 0)

    def test_importing_modules_makes_no_network_calls(self):
        # Fresh process with sockets disabled before any llm_metrics import.
        code = (
            "import socket\n"
            "def blocked(*a, **k): raise AssertionError('network access"
            " attempted')\n"
            "socket.socket.connect = blocked\n"
            "socket.create_connection = blocked\n"
            "import llm_metrics.openai_provider, llm_metrics.real_smoke\n"
            "import llm_metrics.dashboard, llm_metrics.storage,"
            " llm_metrics.__main__\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
