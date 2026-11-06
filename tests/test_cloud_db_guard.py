"""Regression tests for the cloud-origin database guard in real_benchmark.run().

These are offline unit tests: no live database, no network, no paid calls.

The guard fires before the API key is read and before any provider adapter is
constructed, so a cloud-origin invocation with a missing or SQLite URL cannot
reach the payment step even if a valid key happens to be present.

Local-origin invocations are unaffected: they pass through the guard and reach
the existing DB-preflight check, preserving established SQLite development
behavior.
"""

import contextlib
import io
import os
import pathlib
import tempfile
import unittest
from unittest import mock

from llm_metrics import benchmark
from llm_metrics import config
from llm_metrics import real_benchmark
from llm_metrics import storage
from llm_metrics import targets


FAKE_KEY = "sk-fake-key-for-testing-cloud-guard"
_OPENAI_TARGET = next(
    t for t in targets.BENCHMARK_TARGETS if t.provider == "openai"
)


def _run_with_env(
    origin_cloud: str,
    db_url: str,
    *,
    db_connect_error: Exception | None = None,
    with_key: bool = True,
) -> tuple[int, str, str]:
    """Runs real_benchmark.run() under the given environment.

    Args:
        origin_cloud: Value for LLM_METRICS_ORIGIN_CLOUD ("" means local).
        db_url: Value for LLM_METRICS_DATABASE_URL ("" means unset/empty).
        db_connect_error: If not None, storage.connect raises this error.
        with_key: Whether to include a fake provider API key.

    Returns:
        (exit_code, stdout, stderr)
    """
    out, err = io.StringIO(), io.StringIO()
    env_overrides = {
        "LLM_METRICS_ORIGIN_CLOUD": origin_cloud,
        "LLM_METRICS_ORIGIN_REGION": "us-central1",
        config.DATABASE_URL_VARIABLE: db_url,
    }
    if with_key:
        env_overrides[_OPENAI_TARGET.api_key_variable] = FAKE_KEY

    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.dict(os.environ, env_overrides))
        if db_connect_error is not None:
            stack.enter_context(
                mock.patch.object(storage, "connect", side_effect=db_connect_error)
            )
        stack.enter_context(contextlib.redirect_stdout(out))
        stack.enter_context(contextlib.redirect_stderr(err))
        from llm_metrics import workloads
        workload = workloads.get_workload("interactive-chat-v1")
        code = real_benchmark.run(_OPENAI_TARGET, workload, debug=False)
    return code, out.getvalue(), err.getvalue()


class CloudGuardRejectsTest(unittest.TestCase):
    """Cloud-origin invocations without a PostgreSQL URL are refused before
    any provider adapter is constructed or network call is made."""

    def test_gcp_no_url_refuses(self):
        code, _, err = _run_with_env("gcp", "")
        self.assertEqual(code, 2)
        self.assertIn("No request was made", err)

    def test_gcp_no_url_mentions_database_url_variable(self):
        _, _, err = _run_with_env("gcp", "")
        self.assertIn(config.DATABASE_URL_VARIABLE, err)

    def test_gcp_no_url_refuses_even_with_fake_api_key(self):
        # The guard fires before the key is read; having a key does not bypass it.
        code, _, err = _run_with_env("gcp", "", with_key=True)
        self.assertEqual(code, 2)
        self.assertIn("No request was made", err)

    def test_gcp_sqlite_url_refuses(self):
        code, _, err = _run_with_env("gcp", "sqlite:///path/to/db.sqlite")
        self.assertEqual(code, 2)
        self.assertIn("No request was made", err)

    def test_gcp_sqlite_memory_refuses(self):
        code, _, err = _run_with_env("gcp", "sqlite://:memory:")
        self.assertEqual(code, 2)
        self.assertIn("No request was made", err)

    def test_gcp_bare_absolute_path_refuses(self):
        # A bare path has no scheme; it would resolve to container-local storage.
        code, _, err = _run_with_env("gcp", "/home/user/data/llm_metrics.db")
        self.assertEqual(code, 2)
        self.assertIn("No request was made", err)

    def test_gcp_memory_bare_refuses(self):
        code, _, err = _run_with_env("gcp", ":memory:")
        self.assertEqual(code, 2)
        self.assertIn("No request was made", err)

    def test_gcp_unsupported_scheme_refuses(self):
        # mysql:// is not an approved cloud scheme.
        code, _, err = _run_with_env("gcp", "mysql://host/db")
        self.assertEqual(code, 2)
        self.assertIn("No request was made", err)

    def test_non_gcp_cloud_no_url_refuses(self):
        # Any non-local origin, not just "gcp", triggers the guard.
        code, _, err = _run_with_env("aws", "")
        self.assertEqual(code, 2)
        self.assertIn("No request was made", err)

    def test_non_gcp_cloud_sqlite_refuses(self):
        code, _, err = _run_with_env("aws", "sqlite:///data/db.sqlite")
        self.assertEqual(code, 2)
        self.assertIn("No request was made", err)

    def test_guard_error_does_not_echo_url_value(self):
        # The error must not include any database credential or URL content.
        _, _, err = _run_with_env("gcp", "sqlite:///secret/path/db.sqlite")
        self.assertNotIn("secret/path", err)
        self.assertNotIn("sqlite:///", err)

    def test_guard_error_does_not_echo_key(self):
        _, _, err = _run_with_env("gcp", "", with_key=True)
        self.assertNotIn(FAKE_KEY, err)
        self.assertNotIn("sk-fake", err)

    def test_guard_prints_origin_in_error(self):
        _, _, err = _run_with_env("gcp", "")
        self.assertIn("gcp", err)

    def test_guard_no_announcement_printed(self):
        # "About to make" is printed only after all preflight checks pass.
        _, out, _ = _run_with_env("gcp", "")
        self.assertNotIn("About to make", out)


class CloudGuardPassesTest(unittest.TestCase):
    """When the guard passes (PostgreSQL URL for cloud origin, or local origin),
    execution reaches the existing DB-preflight check."""

    def test_gcp_postgresql_url_reaches_db_preflight(self):
        # A PostgreSQL URL passes the guard; an unreachable DB aborts before the
        # paid request with the existing DB-preflight error (not the guard error).
        pg_url = "postgresql://host/llm_metrics"
        code, _, err = _run_with_env(
            "gcp",
            pg_url,
            db_connect_error=OSError("connection refused"),
        )
        self.assertEqual(code, 2)
        # The DB preflight message, not the cloud guard message.
        self.assertIn("database", err.lower())
        self.assertIn("No request was made", err)
        # Not the guard's specific wording.
        self.assertNotIn("ephemeral container storage", err)

    def test_gcp_postgresql_psycopg2_url_reaches_db_preflight(self):
        pg_url = "postgresql+psycopg2://host/llm_metrics"
        code, _, err = _run_with_env(
            "gcp",
            pg_url,
            db_connect_error=OSError("connection refused"),
        )
        self.assertEqual(code, 2)
        self.assertIn("database", err.lower())
        self.assertNotIn("ephemeral container storage", err)

    def test_local_origin_sqlite_reaches_db_preflight(self):
        # Local origin (empty = "local") is not affected by the guard; it still
        # reaches the existing DB-preflight with a SQLite path, as before.
        with tempfile.TemporaryDirectory() as tmp:
            sqlite_url = f"sqlite:///{tmp}/test.db"
            code, _, err = _run_with_env(
                "",
                sqlite_url,
                db_connect_error=OSError("disk error"),
            )
        self.assertEqual(code, 2)
        self.assertIn("database", err.lower())
        # Confirm: the cloud-guard message was NOT the reason for rejection.
        self.assertNotIn("ephemeral container storage", err)
        self.assertNotIn("LLM_METRICS_ORIGIN_CLOUD", err)

    def test_local_origin_explicit_local_sqlite_reaches_preflight(self):
        # Explicitly setting ORIGIN_CLOUD to "local" also bypasses the guard.
        with tempfile.TemporaryDirectory() as tmp:
            sqlite_url = f"sqlite:///{tmp}/test.db"
            code, _, err = _run_with_env(
                "local",
                sqlite_url,
                db_connect_error=RuntimeError("schema mismatch"),
            )
        self.assertEqual(code, 2)
        self.assertNotIn("ephemeral container storage", err)

    def test_db_preflight_error_does_not_echo_credentials(self):
        # The DB-preflight error (from the existing guard, not the cloud guard)
        # must also not echo credentials when reached via a PostgreSQL URL.
        pg_url = "postgresql://user:secret@host/db"
        _, _, err = _run_with_env(
            "gcp",
            pg_url,
            db_connect_error=OSError("refused"),
        )
        self.assertNotIn("user:secret", err)
        self.assertNotIn("secret@", err)
        self.assertNotIn("@host", err)


class CheckCloudDbUrlTest(unittest.TestCase):
    """Unit tests for the _check_cloud_db_url helper."""

    def _check(self, url: str) -> str | None:
        return real_benchmark._check_cloud_db_url(url)

    def test_empty_string_fails(self):
        self.assertIsNotNone(self._check(""))

    def test_sqlite_url_fails(self):
        self.assertIsNotNone(self._check("sqlite:///path/to/db"))

    def test_sqlite_memory_fails(self):
        self.assertIsNotNone(self._check("sqlite://:memory:"))

    def test_bare_path_fails(self):
        self.assertIsNotNone(self._check("/absolute/path/db.sqlite"))

    def test_memory_bare_fails(self):
        self.assertIsNotNone(self._check(":memory:"))

    def test_relative_path_fails(self):
        self.assertIsNotNone(self._check("data/llm_metrics.db"))

    def test_mysql_fails(self):
        self.assertIsNotNone(self._check("mysql://host/db"))

    def test_postgresql_passes(self):
        self.assertIsNone(self._check("postgresql://host/db"))

    def test_postgresql_psycopg2_passes(self):
        self.assertIsNone(self._check("postgresql+psycopg2://host/db"))

    def test_postgresql_with_credentials_passes(self):
        # Credentials in the URL are accepted by the guard; never echoed.
        self.assertIsNone(self._check("postgresql://user:pass@host:5432/db"))

    def test_error_does_not_contain_sqlite_url_value(self):
        err = self._check("sqlite:///secret/path")
        self.assertNotIn("secret/path", err)

    def test_error_does_not_contain_pg_credentials(self):
        # Even if someone passes credentials to the check function,
        # the error message must not echo them.
        err = self._check("mysql://admin:topsecret@host/db")
        self.assertIsNotNone(err)
        self.assertNotIn("topsecret", err)
        self.assertNotIn("admin", err)
