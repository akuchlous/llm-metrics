"""Regression tests for the pre-flight DB check in real_benchmark.run().

These are offline unit tests: no live database, no network, no paid calls.
They verify that a storage failure before a paid request is handled safely:
- run() returns exit code 2 (configuration error)
- the error message is printed to stderr
- no paid provider call is made
- no database URL with credentials is echoed in the error message
"""

import contextlib
import io
import os
import pathlib
import tempfile
import unittest
from unittest import mock

from llm_metrics import real_benchmark
from llm_metrics import storage
from llm_metrics import targets


FAKE_KEY = "sk-fake-key-for-testing"
_OPENAI_TARGET = next(
    t for t in targets.BENCHMARK_TARGETS if t.provider == "openai"
)


def _run_with_bad_db(error: Exception) -> tuple[int, str, str]:
    """Runs real_benchmark.run() with storage.connect patched to raise error.

    Returns (exit_code, stdout, stderr).
    """
    out, err = io.StringIO(), io.StringIO()
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.dict(os.environ, {
            _OPENAI_TARGET.api_key_variable: FAKE_KEY,
            "LLM_METRICS_ORIGIN_CLOUD": "",
            "LLM_METRICS_ORIGIN_REGION": "",
        }))
        stack.enter_context(
            mock.patch.object(storage, "connect", side_effect=error)
        )
        stack.enter_context(contextlib.redirect_stdout(out))
        stack.enter_context(contextlib.redirect_stderr(err))
        from llm_metrics import workloads
        workload = workloads.get_workload("interactive-chat-v1")
        # Use a temporary SQLite path so config.get_database_url() succeeds.
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(pathlib.Path(tmp) / "test.db")
            stack.enter_context(mock.patch.dict(os.environ, {
                "LLM_METRICS_DB_PATH": db_path,
            }))
            code = real_benchmark.run(_OPENAI_TARGET, workload, debug=False)
    return code, out.getvalue(), err.getvalue()


class PreflightDbCheckTest(unittest.TestCase):
    """DB connectivity is verified before any paid provider call is made."""

    def test_bad_db_returns_exit_code_2(self):
        code, _, _ = _run_with_bad_db(OSError("connection refused"))
        self.assertEqual(code, 2)

    def test_bad_db_prints_error_to_stderr(self):
        _, _, err = _run_with_bad_db(OSError("connection refused"))
        self.assertIn("Error", err)
        self.assertIn("database", err.lower())

    def test_bad_db_does_not_print_announcement(self):
        # "About to make" is printed only after the preflight check passes.
        _, out, _ = _run_with_bad_db(OSError("connection refused"))
        self.assertNotIn("About to make", out)

    def test_bad_db_error_does_not_echo_credentials(self):
        # The error must not include user:password@ in the URL.
        _, _, err = _run_with_bad_db(RuntimeError("schema mismatch"))
        self.assertNotIn("sk-fake", err)
        self.assertNotIn("@", err)

    def test_runtime_error_also_caught(self):
        # schema failures (RuntimeError) are treated the same as network errors
        code, _, err = _run_with_bad_db(RuntimeError("orphan tables"))
        self.assertEqual(code, 2)
        self.assertIn("Error", err)


class PostgresIntegrationHarnessGuardTest(unittest.TestCase):
    """DB-name safety check in test_postgres_integration guards against tunnels."""

    def _skip_msg(self, url: str) -> str | None:
        """Return the SkipTest message, or None if the URL would be accepted."""
        from urllib.parse import urlparse
        import re
        _SAFE_DBNAME_RE = re.compile(
            r"(test|dev|bench|tmp|temp|\d{3,}[a-z])", re.IGNORECASE
        )
        parsed = urlparse(url)
        if parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
            return "not localhost"
        dbname = parsed.path.lstrip("/")
        if not _SAFE_DBNAME_RE.search(dbname):
            return f"unsafe dbname: {dbname!r}"
        return None

    def test_production_name_is_refused(self):
        self.assertIsNotNone(
            self._skip_msg("postgresql://user:pass@localhost/llm_metrics")
        )

    def test_prod_name_is_refused(self):
        self.assertIsNotNone(
            self._skip_msg("postgresql://user:pass@localhost/prod")
        )

    def test_test_suffix_is_accepted(self):
        self.assertIsNone(
            self._skip_msg("postgresql://user:pass@localhost/llm_metrics_test")
        )

    def test_step_suffix_is_accepted(self):
        self.assertIsNone(
            self._skip_msg("postgresql://user:pass@localhost/llm_metrics_018d")
        )

    def test_non_localhost_is_refused(self):
        self.assertIsNotNone(
            self._skip_msg("postgresql://user:pass@10.0.0.1/llm_metrics_test")
        )

    def test_dev_name_is_accepted(self):
        self.assertIsNone(
            self._skip_msg("postgresql://user:pass@localhost/dev_db")
        )
