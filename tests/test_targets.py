"""Tests for the benchmark targets, request profiles, and the pilot command.

No test touches the network or spends money: real adapters only ever get a
fake opener, and command tests that must stay offline block sockets.

`storage.load_request` returns None only for an unknown id; tests look up ids
they have just saved, so its result is subscripted directly.
"""

# pylint: disable=unsubscriptable-object

import ast
import contextlib
import dataclasses
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from llm_metrics import anthropic_provider
from llm_metrics import benchmark
from llm_metrics import pricing
from llm_metrics import providers
from llm_metrics import real_benchmark
from llm_metrics import storage
from llm_metrics import targets
from llm_metrics import workloads
from tests import fakes
from tests import test_real_providers as fixtures

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
ORIGIN = ("local", "unknown")
FAKE_KEY = fakes.FAKE_KEY

# Every benchmark target, pinned. A change to any field changes what a stored
# profile id means: add a new profile version instead of editing these.
EXPECTED_TARGETS = {
    "openai.gpt-6-luna.v1": {
        "provider": "openai",
        "model": "gpt-6-luna",
        "output_cap_field": "max_output_tokens",
        "settings": (
            ("store", "false"),
            ("reasoning.effort", '"none"'),
            ("prompt_cache_options.mode", '"explicit"'),
        ),
        "cache_policy": "disabled",
        "api_key_variable": "OPENAI_API_KEY",
    },
    "anthropic.claude-haiku-5-5.v1": {
        "provider": "anthropic",
        "model": "claude-haiku-5-5",
        "output_cap_field": "max_tokens",
        "settings": (("thinking.type", '"disabled"'),),
        "cache_policy": "provider_default",
        "api_key_variable": "ANTHROPIC_API_KEY",
    },
    "google.gemini-3.5-flash-lite.v1": {
        "provider": "google",
        "model": "gemini-3.5-flash-lite",
        "output_cap_field": "generation_config.max_output_tokens",
        "settings": (
            ("store", "false"),
            ("generation_config.thinking_level", '"minimal"'),
        ),
        "cache_policy": "provider_default",
        "api_key_variable": "GEMINI_API_KEY",
    },
    "xai.grok-4.20-0309-non-reasoning.v1": {
        "provider": "xai",
        "model": "grok-4.20-0309-non-reasoning",
        "output_cap_field": "max_output_tokens",
        "settings": (("store", "false"),),
        "cache_policy": "provider_default",
        "api_key_variable": "XAI_API_KEY",
    },
}


def run_dummy(provider, db_path, workload=workloads.INTERACTIVE_CHAT_V1):
    return benchmark.run_attempt(
        provider, workload, "test", db_path, origin=ORIGIN
    )


class RegistryTest(unittest.TestCase):

    def test_exactly_one_pinned_target_per_provider(self):
        self.assertEqual(
            [t.provider for t in targets.BENCHMARK_TARGETS],
            ["openai", "anthropic", "google", "xai"],
        )
        for target in targets.BENCHMARK_TARGETS:
            with self.subTest(profile=target.profile_id):
                expected = EXPECTED_TARGETS[target.profile_id]
                self.assertEqual(
                    {k: getattr(target, k) for k in expected}, expected
                )
                self.assertIs(targets.get_target(target.provider), target)
                self.assertIs(targets.get_profile(target.profile_id), target)

    def test_profiles_are_immutable_and_validated(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            targets.OPENAI.model = "other"  # pytype: disable=attribute-error
        for bad_id in ("openai.gpt-6-luna", "anthropic.gpt-6-luna.v1"):
            with self.subTest(profile_id=bad_id):
                with self.assertRaises(ValueError):
                    dataclasses.replace(targets.OPENAI, profile_id=bad_id)
        with self.assertRaises(ValueError):
            dataclasses.replace(targets.OPENAI, settings=(("store", "nope"),))

    def test_cache_policies_are_explicit_and_never_unknown(self):
        for profile in (targets.SIMULATED, *targets.BENCHMARK_TARGETS):
            with self.subTest(profile=profile.profile_id):
                self.assertIn(profile.cache_policy, providers.CACHE_POLICIES)
                self.assertNotEqual(profile.cache_policy, "unknown")

    def test_reasoning_and_cache_differences_stay_explicit(self):
        # Each profile states its own provider's control; none is described
        # as another provider's equivalent.
        self.assertIn("reasoning.effort=none", targets.OPENAI.reasoning)
        self.assertIn("thinking.type=disabled", targets.ANTHROPIC.reasoning)
        self.assertIn("cannot be turned fully off", targets.GOOGLE.reasoning)
        self.assertIn("non-reasoning", targets.XAI.reasoning)
        self.assertEqual(
            {t.provider: t.cache_policy for t in targets.BENCHMARK_TARGETS},
            {
                "openai": "disabled",
                "anthropic": "provider_default",
                "google": "provider_default",
                "xai": "provider_default",
            },
        )

    def test_unknown_provider_is_refused_without_echo(self):
        for name in ("all", "OpenAI", "", "sk-secret-value"):
            with self.subTest(name=name):
                with self.assertRaises(targets.UnknownTargetError) as ctx:
                    targets.get_target(name)
                self.assertIn(
                    "openai, anthropic, google, xai", str(ctx.exception)
                )
                if name:
                    self.assertNotIn(name, str(ctx.exception))
        self.assertIsNone(targets.get_profile("dummy.dummy-model-v1.v2"))

    def test_settings_merge_into_nested_fields(self):
        body = targets.GOOGLE.apply_settings(
            {"generation_config": {"max_output_tokens": 300}}
        )
        self.assertEqual(
            body,
            {
                "generation_config": {
                    "max_output_tokens": 300,
                    "thinking_level": "minimal",
                },
                "store": False,
            },
        )

    def test_profiles_are_separate_from_workload_identity(self):
        for profile in targets.BENCHMARK_TARGETS:
            settings = json.dumps(profile.settings)
            for workload in workloads.list_workloads():
                self.assertNotIn(workload.workload_id, profile.profile_id)
                self.assertNotIn(workload.prompt[:40], settings)
            for field in ("max_output_tokens", "max_tokens", "input"):
                self.assertNotIn(f'"{field}"', settings)
        self.assertEqual(
            workloads.get_workload("interactive-chat-v1").max_output_tokens,
            300,
        )

    def test_models_are_named_only_in_the_registry_and_prices(self):
        # Selected model ids are not scattered through the code.
        package = REPO_ROOT / "llm_metrics"
        allowed = {"targets.py", "pricing.py"}
        models = {target.model for target in targets.BENCHMARK_TARGETS}
        for path in package.glob("*.py"):
            if path.name in allowed:
                continue
            with self.subTest(file=path.name):
                literals = {
                    node.value
                    for node in ast.walk(ast.parse(path.read_text()))
                    if isinstance(node, ast.Constant)
                }
                self.assertFalse(models & literals)

    def test_targets_module_imports_nothing_from_the_package(self):
        tree = ast.parse((REPO_ROOT / "llm_metrics" / "targets.py").read_text())
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        } | {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        self.assertFalse({m for m in imported if "llm_metrics" in str(m)})


class PricingTest(unittest.TestCase):

    def test_every_target_has_a_verified_price(self):
        expected = {
            "openai": (0.10, 0.50, 0.01),
            "anthropic": (0.10, 0.50, 0.01),
            "google": (0.30, 2.50, 0.03),
            "xai": (1.25, 2.50, 0.20),
        }
        for target in targets.BENCHMARK_TARGETS:
            with self.subTest(provider=target.provider):
                price = pricing.price_for(target.provider, target.model)
                self.assertEqual(
                    (
                        price.input_per_1m,
                        price.output_per_1m,
                        price.cached_input_per_1m,
                    ),
                    expected[target.provider],
                )
                source, verified_on = pricing.PRICE_PROVENANCE[
                    (target.provider, target.model)
                ]
                self.assertTrue(source.startswith("https://"))
                self.assertEqual(verified_on, "2026-11-01")

    def test_every_workload_fits_every_modelled_price_tier(self):
        for target in targets.BENCHMARK_TARGETS:
            limit = pricing.price_for(target.provider, target.model)
            for workload in workloads.list_workloads():
                with self.subTest(
                    provider=target.provider, workload=workload.workload_id
                ):
                    if limit.max_input_tokens is not None:
                        self.assertLessEqual(
                            workload.target_input_tokens * 2,
                            limit.max_input_tokens,
                        )

    def test_cached_tokens_use_the_cached_rate_only_when_reported(self):
        price = pricing.Price(1.0, 2.0, cached_input_per_1m=0.1)
        self.assertEqual(
            pricing.request_cost(1000, 0, price, None)["input_cost"], 0.001
        )
        self.assertEqual(
            pricing.request_cost(1000, 0, price, 0)["input_cost"], 0.001
        )
        self.assertAlmostEqual(
            pricing.request_cost(1000, 0, price, 400)["input_cost"],
            (600 * 1.0 + 400 * 0.1) / 1e6,
            places=15,
        )
        with self.assertRaisesRegex(ValueError, "no cached rate"):
            pricing.request_cost(1000, 0, pricing.Price(1.0, 2.0), 1)


class ProfileEnforcementTest(unittest.TestCase):
    """A population cannot silently mix provider/model/profile facts."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db_path = pathlib.Path(tmp.name) / "x.db"

    def test_dummy_provider_still_works_and_records_its_profile(self):
        _, _, request_id = run_dummy(
            providers.DummyProvider(first_token_delay_s=0), self.db_path
        )
        stored = storage.load_request(self.db_path, request_id)
        self.assertEqual(stored["outcome"], "success")
        self.assertEqual(
            stored["request_profile_id"], "dummy.dummy-model-v1.v1"
        )
        self.assertIsNone(stored["cached_input_price_per_1m"])

    def test_mismatched_or_unregistered_profiles_are_refused(self):
        dummy = providers.DummyProvider(first_token_delay_s=0)
        cases = {
            "no profile": {"request_profile": None},
            "unregistered profile": {
                "request_profile": dataclasses.replace(
                    targets.SIMULATED, reasoning="changed"
                )
            },
            "other model": {"model": "dummy-model-v2"},
            "other cache policy": {"cache_policy": "disabled"},
            "another provider's profile": {
                "request_profile": targets.ANTHROPIC
            },
        }
        for name, attributes in cases.items():
            with self.subTest(case=name):
                provider = providers.DummyProvider(first_token_delay_s=0)
                for attribute, value in attributes.items():
                    setattr(provider, attribute, value)
                with self.assertRaisesRegex(ValueError, "profile"):
                    run_dummy(provider, self.db_path)
        self.assertFalse(self.db_path.exists())
        run_dummy(dummy, self.db_path)  # The registered one still works.

    def test_real_adapter_with_another_model_is_refused_before_calling(self):
        opener = fakes.FakeOpener()
        provider = fixtures.BY_PROVIDER["anthropic"].adapter(
            FAKE_KEY, opener=opener
        )
        provider.model = "claude-sonnet-5-5"
        with self.assertRaisesRegex(ValueError, "profile"):
            run_dummy(provider, self.db_path)
        self.assertEqual(opener.calls, [])

    def test_adapters_declare_their_registered_profile(self):
        for spec in fixtures.SPECS:
            adapter = spec.adapter
            self.assertIs(adapter.request_profile, spec.profile)
            self.assertEqual(
                (adapter.name, adapter.model, adapter.cache_policy),
                (
                    spec.profile.provider,
                    spec.profile.model,
                    spec.profile.cache_policy,
                ),
            )


no_network = fakes.no_network


class RealBenchmarkCommandTest(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db_path = pathlib.Path(tmp.name) / "x.db"

    def run_main(self, argv, env=None, opener=None):
        out, err = io.StringIO(), io.StringIO()
        environ = {
            "LLM_METRICS_DB_PATH": str(self.db_path),
            "LLM_METRICS_ORIGIN_CLOUD": "",
            "LLM_METRICS_ORIGIN_REGION": "",
            **(env or {}),
        }
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.dict(os.environ, environ))
            for target in targets.BENCHMARK_TARGETS:
                if target.api_key_variable not in (env or {}):
                    os.environ.pop(target.api_key_variable, None)
            if opener is not None:
                adapters = {
                    name: (lambda key, cls=cls: cls(key, opener=opener))
                    for name, cls in real_benchmark.ADAPTERS.items()
                }
                stack.enter_context(
                    mock.patch.dict(real_benchmark.ADAPTERS, adapters)
                )
            stack.enter_context(contextlib.redirect_stdout(out))
            stack.enter_context(contextlib.redirect_stderr(err))
            code = real_benchmark.main(argv)
        return code, out.getvalue(), err.getvalue()

    @no_network
    def test_refusals_happen_before_any_request(self):
        cases = {
            "no arguments": [],
            "no --real": ["--provider", "anthropic"],
            "no provider": ["--real"],
            "all providers": ["--provider", "all", "--real"],
            "unknown provider": ["--provider", "mistral", "--real"],
            "repeated provider": [
                "--provider",
                "xai",
                "--provider",
                "google",
                "--real",
            ],
            "unknown workload": [
                "--provider",
                "xai",
                "--workload",
                "nope-v1",
                "--real",
            ],
            "missing value": ["--real", "--provider"],
            "unknown option": ["--provider", "xai", "--real", "--loop"],
        }
        every_key = {
            t.api_key_variable: FAKE_KEY for t in targets.BENCHMARK_TARGETS
        }
        for name, argv in cases.items():
            with self.subTest(case=name):
                code, out, err = self.run_main(argv, env=every_key)
                self.assertEqual(code, 2)
                self.assertIn("Error", err)
                self.assertNotIn("About to make", out)
                self.assertNotIn("mistral", err)
                self.assertNotIn("nope-v1", err)
        self.assertFalse(self.db_path.exists())

    @no_network
    def test_missing_credentials_fail_before_network(self):
        for target in targets.BENCHMARK_TARGETS:
            with self.subTest(provider=target.provider):
                # Other providers' keys are set: only the chosen one counts.
                others = {
                    t.api_key_variable: FAKE_KEY
                    for t in targets.BENCHMARK_TARGETS
                    if t is not target
                }
                code, _, err = self.run_main(
                    ["--provider", target.provider, "--real"], env=others
                )
                self.assertEqual(code, 2)
                self.assertIn(f"{target.api_key_variable} is not set", err)
                self.assertNotIn(FAKE_KEY, err)
        self.assertFalse(self.db_path.exists())

    @no_network
    def test_invalid_origin_is_refused_before_any_request(self):
        code, _, err = self.run_main(
            ["--provider", "xai", "--real"],
            env={"XAI_API_KEY": FAKE_KEY, "LLM_METRICS_ORIGIN_CLOUD": "AWS!"},
        )
        self.assertEqual(code, 2)
        self.assertIn("No request was made", err)

    def test_one_call_to_the_chosen_provider_only(self):
        for spec in fixtures.SPECS:
            with self.subTest(provider=spec.profile.provider):
                opener = fakes.FakeOpener(
                    response=fakes.FakeResponse(
                        spec.body(texts=("Secret", " reply")),
                        spec.request_id_headers,
                    )
                )
                every_key = {
                    t.api_key_variable: FAKE_KEY
                    for t in targets.BENCHMARK_TARGETS
                }
                code, out, err = self.run_main(
                    ["--provider", spec.profile.provider, "--real"],
                    env=every_key,
                    opener=opener,
                )
                self.assertEqual(code, 0, err)
                self.assertEqual(len(opener.calls), 1)
                self.assertEqual(opener.calls[0][0].full_url, spec.url)
                for line in (
                    f"  Provider: {spec.profile.provider}",
                    f"  Model: {spec.profile.model}",
                    f"  Request profile: {spec.profile.profile_id}",
                    f"  Cache policy: {spec.profile.cache_policy}",
                    "  Workload: interactive-chat-v1 (about 2000 input tokens"
                    " estimated; max output tokens 300)",
                    "  Origin: local / unknown",
                    "Outcome: success",
                ):
                    self.assertIn(line, out)
                for secret in (
                    FAKE_KEY,
                    workloads.INTERACTIVE_CHAT_V1.prompt[:200],
                    "Secret reply",
                ):
                    self.assertNotIn(secret, out + err)
        stored = storage.load_recent_requests(self.db_path, "prod", 10)
        self.assertEqual(
            sorted(r["request_profile_id"] for r in stored),
            sorted(s.profile.profile_id for s in fixtures.SPECS),
        )
        self.assertEqual(
            {r["workload_id"] for r in stored}, {"interactive-chat-v1"}
        )
        self.assertEqual(
            storage.load_recent_requests(self.db_path, "test", 10), []
        )

    def test_openai_target_is_available_through_the_same_command(self):
        opener = fakes.FakeOpener(
            response=fakes.FakeResponse(
                fakes.sse(
                    {"type": "response.output_text.delta", "delta": "Hi"},
                    {
                        "type": "response.completed",
                        "response": {
                            "usage": {"input_tokens": 1900, "output_tokens": 9}
                        },
                    },
                )
            )
        )
        code, out, _ = self.run_main(
            ["--provider", "openai", "--real", "--workload", "coding-v1"],
            env={"OPENAI_API_KEY": FAKE_KEY},
            opener=opener,
        )
        self.assertEqual(code, 0)
        self.assertIn("Workload: coding-v1", out)
        body = json.loads(opener.calls[0][0].data)
        self.assertEqual(body["max_output_tokens"], 1000)

    def test_rejected_request_is_not_recorded(self):
        spec = fixtures.BY_PROVIDER["anthropic"]
        opener = fakes.FakeOpener(error=fixtures.http_error(spec, 401))
        code, _, err = self.run_main(
            ["--provider", "anthropic", "--real", "--debug"],
            env={"ANTHROPIC_API_KEY": FAKE_KEY},
            opener=opener,
        )
        self.assertEqual(code, 2)
        self.assertIn("Anthropic rejected the request (HTTP 401)", err)
        self.assertIn("Debug (sanitized, not stored)", err)
        self.assertNotIn(FAKE_KEY, err)
        self.assertEqual(
            storage.load_recent_requests(self.db_path, "prod", 5), []
        )

    def test_recorded_failure_shows_debug_diagnostics(self):
        spec = fixtures.BY_PROVIDER["google"]
        opener = fakes.FakeOpener(error=fixtures.http_error(spec, 503))
        code, out, err = self.run_main(
            ["--provider", "google", "--real", "--debug"],
            env={"GEMINI_API_KEY": FAKE_KEY},
            opener=opener,
        )
        self.assertEqual(code, 0)
        self.assertIn("FAILED", out)
        self.assertIn("http_status=503", err)

    def test_refuses_as_a_process_without_keys(self):
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in {t.api_key_variable for t in targets.BENCHMARK_TARGETS}
        }
        env["LLM_METRICS_DB_PATH"] = str(self.db_path)
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "llm_metrics.real_benchmark",
                "--provider",
                "anthropic",
                "--real",
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("ANTHROPIC_API_KEY is not set", proc.stderr)
        self.assertFalse(self.db_path.exists())

    def test_importing_provider_modules_makes_no_network_calls(self):
        code = (
            "import socket, urllib.request\n"
            "def blocked(*a, **k): raise AssertionError('network access"
            " attempted')\n"
            "socket.socket.connect = blocked\n"
            "socket.create_connection = blocked\n"
            "urllib.request.urlopen = blocked\n"
            "import llm_metrics.anthropic_provider\n"
            "import llm_metrics.google_provider\n"
            "import llm_metrics.xai_provider, llm_metrics.http_streaming\n"
            "import llm_metrics.targets, llm_metrics.real_benchmark\n"
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

    def test_simulated_paths_never_import_real_adapters(self):
        real = {
            "anthropic_provider",
            "google_provider",
            "openai_provider",
            "real_benchmark",
            "xai_provider",
        }
        for module in ("__main__.py", "config.py", "seed_history.py", "web.py"):
            tree = ast.parse((REPO_ROOT / "llm_metrics" / module).read_text())
            imported = {
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
                for alias in node.names
            }
            with self.subTest(module=module):
                self.assertFalse(imported & real)


class AdapterInterfaceTest(unittest.TestCase):

    def test_rejections_share_one_base_class(self):
        self.assertTrue(
            issubclass(
                anthropic_provider.RequestRejected,
                real_benchmark.http_streaming.RequestRejected,
            )
        )


if __name__ == "__main__":
    unittest.main()
