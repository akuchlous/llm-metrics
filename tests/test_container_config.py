"""Offline tests for Dockerfile / .dockerignore consistency.

These tests verify that every file explicitly COPYed in the Dockerfile is
reachable in the build context, i.e. not excluded by .dockerignore.  They
run entirely from the filesystem — no Docker daemon required.

The key regression: .dockerignore excluded `scripts/` while the Dockerfile
COPYed `scripts/install_requirements.py`; the image would have silently
failed to find the installer.
"""

import pathlib
import re
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCKERFILE = REPO_ROOT / "Dockerfile"
DOCKERIGNORE = REPO_ROOT / ".dockerignore"


def _dockerfile_copy_sources() -> list[str]:
    """Returns the source paths from every COPY instruction in the Dockerfile.

    For `COPY a b`, returns `a`.  For `COPY a/ b/`, returns `a/`.
    """
    sources = []
    for line in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.upper().startswith("COPY "):
            # Strip inline comments
            line = re.sub(r"\s*#.*$", "", line)
            parts = line.split()
            # COPY <src> <dst>  — parts[0] is COPY, parts[-1] is dst, rest are src
            if len(parts) >= 3:
                sources.extend(parts[1:-1])
    return sources


def _dockerignore_excludes(path: str) -> bool:
    """Returns True if .dockerignore definitively excludes `path`.

    Implements the Docker pattern rules:
    - Lines starting with `!` are negations (re-includes).
    - Patterns are matched left-to-right; the last matching rule wins.
    - `dir/` matches the directory and everything under it.
    - `*` matches everything in one path segment.

    This is a simplified check sufficient for our patterns.
    """
    rules = []
    for line in DOCKERIGNORE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        negate = line.startswith("!")
        pattern = line[1:] if negate else line
        rules.append((pattern, negate))

    excluded = False
    for pattern, negate in rules:
        # Match: exact name, name/ prefix (directory), or simple wildcard
        if pattern.endswith("/"):
            # Directory pattern: matches any path starting with that prefix
            matched = path.startswith(pattern) or path == pattern.rstrip("/")
        elif "*" in pattern:
            matched = bool(re.fullmatch(pattern.replace("*", "[^/]*"), path))
        else:
            matched = path == pattern or path.startswith(pattern + "/")
        if matched:
            excluded = not negate
    return excluded


@unittest.skipUnless(
    DOCKERFILE.exists() and DOCKERIGNORE.exists(),
    "Dockerfile and .dockerignore not present — skipped outside repo root",
)
class DockerfileDockerignoreConsistencyTest(unittest.TestCase):
    """Every COPY source in the Dockerfile must reach the build context."""

    def test_dockerfile_exists(self):
        self.assertTrue(DOCKERFILE.exists(), "Dockerfile not found")

    def test_dockerignore_exists(self):
        self.assertTrue(DOCKERIGNORE.exists(), ".dockerignore not found")

    def test_copy_sources_not_excluded_by_dockerignore(self):
        """No COPYed source path may be definitively excluded by .dockerignore."""
        sources = _dockerfile_copy_sources()
        self.assertTrue(sources, "No COPY instructions found in Dockerfile")
        blocked = [s for s in sources if _dockerignore_excludes(s)]
        self.assertEqual(
            blocked,
            [],
            f"Dockerfile COPYs path(s) excluded by .dockerignore: {blocked}. "
            "Add a negation rule (e.g. '!scripts/install_requirements.py') or "
            "remove the exclusion.",
        )

    def test_install_script_not_excluded(self):
        """scripts/install_requirements.py must be reachable in the build context."""
        self.assertFalse(
            _dockerignore_excludes("scripts/install_requirements.py"),
            "scripts/install_requirements.py is excluded by .dockerignore "
            "but is required by the Dockerfile RUN step.",
        )

    def test_secrets_excluded(self):
        """Key secret/credential patterns must be excluded from the build context."""
        for pattern in [".env", "data/", ".venv/"]:
            with self.subTest(pattern=pattern):
                self.assertTrue(
                    _dockerignore_excludes(pattern),
                    f"{pattern!r} should be excluded from the Docker build context",
                )
