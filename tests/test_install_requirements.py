"""Tests for scripts/install_requirements.py and requirements.txt.

Downloads and pip runs are mocked: no test reaches the network or changes the
real environment.
"""

import contextlib
import hashlib
import importlib.util
import io
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "install_requirements", REPO_ROOT / "scripts" / "install_requirements.py"
)
installer = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(installer)

FAKE_ZIPAPP = b"fake pip zipapp"


def completed(returncode):
    return subprocess.CompletedProcess(args=[], returncode=returncode)


class InstallerTest(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.requirements = pathlib.Path(tmp.name) / "requirements.txt"
        self.requirements.write_text("Flask==1.0 --hash=sha256:abc\n")
        self.stamp = pathlib.Path(tmp.name) / "stamp"
        for name, value in (
            ("REQUIREMENTS", self.requirements),
            ("STAMP", self.stamp),
            ("PIP_ZIPAPP_SHA256", hashlib.sha256(FAKE_ZIPAPP).hexdigest()),
        ):
            patcher = mock.patch.object(installer, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        # Every subprocess (pip) call and download goes to these mocks.
        run_patcher = mock.patch.object(
            installer.subprocess, "run", return_value=completed(0)
        )
        self.run_mock = run_patcher.start()
        self.addCleanup(run_patcher.stop)
        urlopen_patcher = mock.patch.object(
            installer.urllib.request,
            "urlopen",
            side_effect=lambda *args, **kwargs: io.BytesIO(FAKE_ZIPAPP),
        )
        self.urlopen = urlopen_patcher.start()
        self.addCleanup(urlopen_patcher.stop)

    def main(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = installer.main()
        return code, out.getvalue(), err.getvalue()

    def pip_install_call(self):
        """The argv of the (last) pip install call."""
        calls = [c.args[0] for c in self.run_mock.call_args_list]
        installs = [argv for argv in calls if "install" in argv]
        self.assertEqual(len(installs), 1)
        return installs[0]

    def test_up_to_date_environment_does_nothing(self):
        self.stamp.write_text(installer.requirements_digest() + "\n")
        code, out, _ = self.main()
        self.assertEqual(code, 0)
        self.assertIn("Dependencies ready", out)
        self.run_mock.assert_not_called()
        self.urlopen.assert_not_called()

    def test_changed_requirements_trigger_a_reinstall(self):
        self.stamp.write_text("digest-of-older-requirements\n")
        self.assertFalse(installer.is_up_to_date())

    def test_existing_pip_is_used_without_download(self):
        code, out, _ = self.main()
        self.assertEqual(code, 0)
        self.assertIn("Dependencies installed", out)
        self.urlopen.assert_not_called()
        argv = self.pip_install_call()
        self.assertEqual(argv[:3], [sys.executable, "-m", "pip"])
        for flag in ("--require-hashes", "--only-binary=:all:", "--isolated"):
            self.assertIn(flag, argv)
        self.assertEqual(argv[-1], str(self.requirements))
        self.assertEqual(
            self.stamp.read_text().strip(), installer.requirements_digest()
        )

    def test_missing_pip_uses_the_verified_zipapp(self):
        self.run_mock.side_effect = lambda argv, **k: completed(
            1 if argv[1:3] == ["-m", "pip"] else 0
        )
        code, _, _ = self.main()
        self.assertEqual(code, 0)
        self.urlopen.assert_called_once()
        self.assertEqual(
            self.urlopen.call_args.args[0], installer.PIP_ZIPAPP_URL
        )
        argv = self.pip_install_call()
        self.assertEqual(argv[0], sys.executable)
        self.assertTrue(argv[1].endswith("pip.pyz"))
        self.assertTrue(self.stamp.exists())

    def test_zipapp_with_wrong_hash_is_never_run(self):
        self.run_mock.side_effect = lambda argv, **k: completed(
            1 if argv[1:3] == ["-m", "pip"] else 0
        )
        self.urlopen.side_effect = lambda *a, **k: io.BytesIO(b"tampered")
        code, _, err = self.main()
        self.assertEqual(code, 1)
        self.assertIn("does not match its pinned sha256", err)
        self.assertEqual(len(self.run_mock.call_args_list), 1)  # pip check only
        self.assertFalse(self.stamp.exists())

    def test_download_failure_is_reported(self):
        self.run_mock.side_effect = lambda argv, **k: completed(
            1 if argv[1:3] == ["-m", "pip"] else 0
        )
        self.urlopen.side_effect = OSError("offline")
        code, _, err = self.main()
        self.assertEqual(code, 1)
        self.assertIn("network connection is needed", err)
        self.assertFalse(self.stamp.exists())

    def test_failed_install_leaves_no_stamp(self):
        self.run_mock.side_effect = lambda argv, **k: completed(
            1 if "install" in argv else 0
        )
        code, _, err = self.main()
        self.assertEqual(code, 1)
        self.assertIn("could not install", err)
        self.assertFalse(self.stamp.exists())


class RequirementsFileTest(unittest.TestCase):
    """requirements.txt pins every package exactly, with hashes."""

    def requirements(self):
        text = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
        logical = re.sub(r"\\\n\s*", " ", text)  # join continuation lines
        entries = {}
        for line in logical.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            requirement, *options = line.split()
            name, _, version = requirement.partition("==")
            entries[name.lower()] = (version, options)
        return entries

    def test_every_package_is_pinned_with_hashes(self):
        for name, (version, options) in self.requirements().items():
            with self.subTest(package=name):
                self.assertRegex(version, r"^\d+(\.\d+)+$")
                hashes = [o for o in options if o.startswith("--hash=sha256:")]
                self.assertTrue(hashes)
                self.assertEqual(len(hashes), len(options))
                for option in hashes:
                    self.assertRegex(option, r"^--hash=sha256:[0-9a-f]{64}$")

    def test_flask_and_exactly_its_dependencies(self):
        self.assertEqual(
            set(self.requirements()),
            {
                "flask",
                "werkzeug",
                "jinja2",
                "itsdangerous",
                "click",
                "blinker",
                "markupsafe",
            },
        )


if __name__ == "__main__":
    unittest.main()
