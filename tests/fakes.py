"""Fake HTTP plumbing shared by the provider and command tests.

Every real adapter takes a `urlopen`-compatible opener; tests pass a
`FakeOpener` so no request reaches the network, and wrap tests that must stay
offline in `no_network`.
"""

import io
import json
from unittest import mock

FAKE_KEY = "fake-test-key-NEVER-SHOW-THIS-0123456789"
# Free text that must never appear in diagnostics, output, or storage.
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
    """Records every request and returns one canned response (or raises)."""

    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def __call__(self, request, timeout):
        self.calls.append((request, timeout))
        if self.error is not None:
            raise self.error
        return self.response


def no_network(test):
    """Decorator: any attempt to open a socket or URL fails the test."""

    def blocked(*args, **kwargs):
        raise AssertionError("network access attempted")

    test = mock.patch("socket.socket.connect", blocked)(test)
    test = mock.patch("urllib.request.urlopen", blocked)(test)
    return test
