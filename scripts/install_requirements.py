"""Installs requirements.txt into the running Python environment, verified.

Usage (run.sh does this): .venv/bin/python scripts/install_requirements.py

Every package is installed with `pip --require-hashes --only-binary=:all:`, so
only the exact, hash-pinned wheels in requirements.txt can be installed and
nothing is built from source.

The project venv is created without pip (`venv --without-pip`), because
Debian's `python3-venv` package, which provides `ensurepip`, is missing on
some Chromebooks. When the environment has no pip, this script downloads
pip's official single-file zipapp at a pinned version, verifies its sha256,
runs it once, and deletes it.

A stamp file in the environment records the sha256 of the requirements that
were installed, so later runs make no network request until requirements.txt
changes. Standard library only: it must run before any dependency exists.
"""

import hashlib
import pathlib
import subprocess
import sys
import tempfile
import urllib.request

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
REQUIREMENTS = REPO_ROOT / "requirements.txt"
# Inside the environment being provisioned, so a new venv starts unstamped.
STAMP = pathlib.Path(sys.prefix) / "llm-metrics-requirements.sha256"

# pip's official zipapp, pinned by version and content hash. Chosen at least
# two weeks after release.
PIP_ZIPAPP_URL = "https://bootstrap.pypa.io/pip/zipapp/pip-26.2.1.pyz"
PIP_ZIPAPP_SHA256 = (
    "91d5fd9f6f25549fd839c60536c6f1b945316ce3588d34a605635b6071c91526"
)
DOWNLOAD_TIMEOUT_S = 60

PIP_INSTALL_ARGS = (
    "install",
    "--require-hashes",
    "--only-binary=:all:",
    # Ignore user/global pip configuration and environment variables, so the
    # result does not depend on the machine.
    "--isolated",
    "--disable-pip-version-check",
    "--no-input",
    "--requirement",
)


class InstallError(Exception):
    """Dependencies could not be installed; the message says why."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def requirements_digest() -> str:
    """Returns the sha256 of requirements.txt, which identifies its content."""
    return _sha256(REQUIREMENTS.read_bytes())


def is_up_to_date() -> bool:
    """Whether this environment already has exactly these requirements."""
    try:
        return (
            STAMP.read_text(encoding="utf-8").strip() == requirements_digest()
        )
    except FileNotFoundError:
        return False


def _has_pip() -> bool:
    result = subprocess.run(
        [sys.executable, "-m", "pip", "--version"],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def _download_pip_zipapp(directory: pathlib.Path) -> pathlib.Path:
    """Downloads the pinned pip zipapp and verifies it before it can run.

    Raises:
        InstallError: If the download fails or the content hash differs.
    """
    try:
        with urllib.request.urlopen(
            PIP_ZIPAPP_URL, timeout=DOWNLOAD_TIMEOUT_S
        ) as response:
            content = response.read()
    except OSError as e:
        raise InstallError(
            f"could not download pip from {PIP_ZIPAPP_URL} ({e})."
            " A network connection is needed the first time."
        ) from None
    if _sha256(content) != PIP_ZIPAPP_SHA256:
        raise InstallError(
            "the downloaded pip zipapp does not match its pinned sha256;"
            " refusing to run it."
        )
    path = directory / "pip.pyz"
    path.write_bytes(content)
    return path


def install() -> None:
    """Installs requirements.txt with hash checking, then writes the stamp.

    Raises:
        InstallError: If pip cannot be obtained or the install fails. The
            stamp is not written, so the next run tries again.
    """
    with tempfile.TemporaryDirectory() as tmp:
        if _has_pip():
            pip = [sys.executable, "-m", "pip"]
        else:
            pip = [sys.executable, str(_download_pip_zipapp(pathlib.Path(tmp)))]
        result = subprocess.run(
            [*pip, *PIP_INSTALL_ARGS, str(REQUIREMENTS)], check=False
        )
    if result.returncode != 0:
        raise InstallError("pip could not install requirements.txt.")
    STAMP.write_text(requirements_digest() + "\n", encoding="utf-8")


def main() -> int:
    """Ensures the dependencies are installed.

    Returns:
        Process exit code: 0 when the environment is ready, 1 otherwise.
    """
    if is_up_to_date():
        print("✓ Dependencies ready")
        return 0
    # Flush so this line appears before pip's own output.
    print("  Installing dependencies from requirements.txt ...", flush=True)
    try:
        install()
    except InstallError as e:
        print(f"✗ Could not install dependencies: {e}", file=sys.stderr)
        return 1
    print("✓ Dependencies installed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
