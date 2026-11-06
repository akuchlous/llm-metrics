"""Tests of `./run.sh`.

Verifies the Docker prerequisite checks, usage errors, and mode validation.
Full Docker workflow (tests, seed, measure, dashboard) is verified in Cloud
Shell where Docker is available; see prompts/019-output.md for the results.
"""

import os
import pathlib
import subprocess
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
RUN_SH = REPO_ROOT / "run.sh"


def _run_sh(*args, extra_path_first=None, timeout=10):
    """Run run.sh with optional PATH prefix to control which docker is found."""
    env = dict(os.environ)
    if extra_path_first is not None:
        env["PATH"] = str(extra_path_first) + ":" + env.get("PATH", "/usr/bin:/bin")
    return subprocess.run(
        ["bash", str(RUN_SH)] + list(args),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _make_fake_docker(directory, *, reject_compose=False):
    """Write a minimal fake docker stub into directory.

    If reject_compose is True, the stub returns success for 'docker compose
    version' (so the first prerequisite check passes) but exits non-zero for
    all other compose commands (so compose check fails when tested separately).
    By default the stub accepts 'docker compose version' and exits 0 otherwise.
    """
    p = pathlib.Path(directory) / "docker"
    if reject_compose:
        p.write_text(
            "#!/bin/sh\n"
            # 'docker compose version' — fail to simulate no Compose
            'if [ "$1" = "compose" ] && [ "$2" = "version" ]; then exit 1; fi\n'
            "exit 0\n"
        )
    else:
        p.write_text(
            "#!/bin/sh\n"
            # Accept 'docker compose version' with plausible output
            'if [ "$1" = "compose" ] && [ "$2" = "version" ]; then\n'
            '    echo "Docker Compose version v2.99.0"\n'
            "    exit 0\n"
            "fi\n"
            # For 'docker compose down', record args and exit 0
            "exit 0\n"
        )
    p.chmod(0o755)
    return p


class RunScriptTest(unittest.TestCase):

    def test_is_executable(self):
        self.assertTrue(os.access(RUN_SH, os.X_OK))

    def test_bash_syntax(self):
        subprocess.run(["bash", "-n", str(RUN_SH)], check=True)

    def test_no_docker_exits_nonzero_with_helpful_message(self):
        """run.sh exits non-zero and mentions Docker when docker is absent."""
        with tempfile.TemporaryDirectory() as empty_bin:
            # empty_bin has no docker; command -v docker will fail
            result = _run_sh(extra_path_first=empty_bin)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Docker", result.stderr)

    def test_no_compose_exits_nonzero_with_helpful_message(self):
        """run.sh exits non-zero and mentions compose when Compose v2 is absent."""
        with tempfile.TemporaryDirectory() as fake_bin:
            _make_fake_docker(fake_bin, reject_compose=True)
            result = _run_sh(extra_path_first=fake_bin)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("compose", result.stderr.lower())

    def test_invalid_mode_prints_usage(self):
        """run.sh exits non-zero with usage text for an unrecognised mode."""
        with tempfile.TemporaryDirectory() as fake_bin:
            _make_fake_docker(fake_bin)
            result = _run_sh("badmode", extra_path_first=fake_bin)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Usage:", result.stderr)

    def test_valid_modes_accepted(self):
        """run.sh recognises serve, test and down without a usage error."""
        with tempfile.TemporaryDirectory() as fake_bin:
            _make_fake_docker(fake_bin)
            # 'down' runs 'docker compose down -v --remove-orphans' and exits 0.
            result = _run_sh("down", extra_path_first=fake_bin)
        # down succeeds (fake docker accepts the compose down call)
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("Usage:", result.stderr)
