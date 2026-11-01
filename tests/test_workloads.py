"""Tests for the workload catalogue (`llm_metrics.workloads`) and its use.

Covers the catalogue contract (ids, versions, caps, deterministic content),
the pinned content of every released version, and how `benchmark.run_attempt`
uses a workload: the canonical prompt and cap are sent once, the versioned id
is stored, and provider-reported token counts stay the recorded facts. No test
reaches a network or a paid provider.
"""

import ast
import dataclasses
import hashlib
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest

from llm_metrics import benchmark
from llm_metrics import providers
from llm_metrics import real_smoke
from llm_metrics import storage
from llm_metrics import workloads

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
ORIGIN = ("local", "unknown")

# The documented catalogue: id -> (category, version, max output tokens,
# approximate input-size target in tokens).
CATALOGUE = {
    "interactive-chat-v1": ("interactive_chat", 1, 300, 2_000),
    "coding-v1": ("coding", 1, 1_000, 8_000),
    "rag-v1": ("rag", 1, 500, 16_000),
    "summarization-v1": ("summarization", 1, 1_000, 32_000),
    "extraction-v1": ("extraction", 1, 150, 4_000),
    "agent-tool-v1": ("agent_tool", 1, 300, 8_000),
}

# SHA-256 of every released prompt. If one of these fails, a released
# workload's content changed: restore it, and put the new content under a new
# version (e.g. rag-v2) instead. Never update a hash to make the test pass.
PROMPT_SHA256 = {
    "interactive-chat-v1": (
        "db88e2b5d4062156947121340cc2e6c7424af437ee11ad50b11cf04397a0b625"
    ),
    "coding-v1": (
        "5f27e575e50e94601aa4c6580e3b03c7d0e682bbb975f3456ac637dc65179eae"
    ),
    "rag-v1": (
        "f8e606a7ca8a9c76135b4d5ba2869f3a77dd2cab33ac22d7ba215cc74882dfb1"
    ),
    "summarization-v1": (
        "db06dfd0881e5abe043e7d1733f2a4f5762d066776add42474a242c9cc631578"
    ),
    "extraction-v1": (
        "cccb2b00ba1b3f79a0077f0cf9b3ec2b298e3860be76b3cee9bda4d4cae60bec"
    ),
    "agent-tool-v1": (
        "ee5387f78c8f4fd236e55c7193c2e1da52cea8e027f14518c3323ce8de410ed3"
    ),
    "smoke.short_text.v2": (
        "eb7a774ae209a895cb2877ed9213cf28de285f150d6f963de61e5aff699ebc8a"
    ),
}


class RecordingProvider(providers.LLMProvider):
    """Records what it was sent and reports fixed, provider-style usage.

    Priced like the dummy provider. Its token counts deliberately differ from
    any workload's size target, as a real provider's would.
    """

    name = providers.DummyProvider.name
    model = providers.DummyProvider.model
    request_profile = providers.DummyProvider.request_profile

    def __init__(self, input_tokens=12_345, output_tokens=3):
        self.calls = []
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens

    def stream(self, prompt, max_output_tokens):
        self.calls.append((prompt, max_output_tokens))
        yield "Short"
        yield " answer."
        yield providers.Usage(
            input_tokens=self.input_tokens, output_tokens=self.output_tokens
        )


class CatalogueTest(unittest.TestCase):

    def test_the_six_documented_benchmark_workloads_exist(self):
        self.assertEqual(
            {
                w.workload_id: (
                    w.category,
                    w.version,
                    w.max_output_tokens,
                    w.target_input_tokens,
                )
                for w in workloads.BENCHMARK_WORKLOADS
            },
            CATALOGUE,
        )
        self.assertEqual(
            [w.workload_id for w in workloads.list_workloads()],
            [*CATALOGUE, "smoke.short_text.v2"],
        )

    def test_ids_are_unique_canonical_and_versioned(self):
        ids = [w.workload_id for w in workloads.list_workloads()]
        self.assertEqual(len(ids), len(set(ids)))
        for workload in workloads.BENCHMARK_WORKLOADS:
            with self.subTest(workload=workload.workload_id):
                # One canonical form: "<category with dashes>-v<version>".
                expected = (
                    f"{workload.category.replace('_', '-')}-v{workload.version}"
                )
                self.assertEqual(workload.workload_id, expected)
        categories = [w.category for w in workloads.BENCHMARK_WORKLOADS]
        self.assertEqual(len(categories), len(set(categories)))
        self.assertEqual(set(workloads.CATEGORIES), {*categories, "smoke"})

    def test_fields_are_meaningful(self):
        for workload in workloads.list_workloads():
            with self.subTest(workload=workload.workload_id):
                for text in (workload.name, workload.description):
                    self.assertTrue(text.strip())
                    self.assertEqual(text, text.strip())
                self.assertGreater(workload.max_output_tokens, 0)
                self.assertGreater(len(workload.prompt), 20)

    def test_lookup_returns_the_canonical_definition(self):
        for workload in workloads.list_workloads():
            self.assertIs(
                workloads.get_workload(workload.workload_id), workload
            )
        self.assertEqual(workloads.DEFAULT_WORKLOAD_ID, "interactive-chat-v1")

    def test_unknown_id_fails_clearly_without_echoing_it(self):
        for bad in ("rag-v2", "RAG-v1", "", "rag-v1 ", "<script>"):
            with self.subTest(workload_id=bad):
                with self.assertRaises(workloads.UnknownWorkloadError) as ctx:
                    workloads.get_workload(bad)
                message = str(ctx.exception)
                self.assertIn("rag-v1", message)  # lists the valid ids
                if bad not in ("", "rag-v1 "):
                    self.assertNotIn(bad, message)
        self.assertTrue(issubclass(workloads.UnknownWorkloadError, ValueError))

    def test_definitions_are_immutable(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            workloads.RAG_V1.max_output_tokens = 5000

    def test_incoherent_definitions_are_rejected(self):
        valid = dataclasses.asdict(workloads.RAG_V1)
        for change in (
            {"workload_id": "rag-v2"},  # suffix does not match version
            {"workload_id": "rag"},  # not versioned
            {"workload_id": "Rag-v1"},
            {"category": "chat"},
            {"name": " "},
            {"description": ""},
            {"prompt": "\n"},
            {"max_output_tokens": 0},
            {"target_input_tokens": 0},
        ):
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    workloads.Workload(**{**valid, **change})


class DeterministicContentTest(unittest.TestCase):

    def test_released_prompts_are_unchanged(self):
        self.assertEqual(
            set(PROMPT_SHA256),
            {w.workload_id for w in workloads.list_workloads()},
        )
        for workload in workloads.list_workloads():
            with self.subTest(workload=workload.workload_id):
                digest = hashlib.sha256(workload.prompt.encode()).hexdigest()
                self.assertEqual(
                    digest,
                    PROMPT_SHA256[workload.workload_id],
                    "Released workload content changed; add a new version"
                    " instead.",
                )

    def test_prompts_are_identical_in_a_fresh_process(self):
        # Same text in another interpreter with a different hash seed: no
        # dependence on randomness, ordering, time, or environment.
        code = (
            "import hashlib\n"
            "from llm_metrics import workloads\n"
            "for w in workloads.list_workloads():\n"
            "    print(w.workload_id,"
            " hashlib.sha256(w.prompt.encode()).hexdigest())\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=REPO_ROOT,
            env={"PYTHONHASHSEED": "12345", "PATH": ""},
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            dict(line.split() for line in proc.stdout.splitlines()),
            PROMPT_SHA256,
        )

    def test_prompts_are_near_their_approximate_size_targets(self):
        # About 4 characters per token: a design check only. Providers report
        # their own counts, which will differ.
        for workload in workloads.BENCHMARK_WORKLOADS:
            with self.subTest(workload=workload.workload_id):
                approximate_tokens = len(workload.prompt) / 4
                ratio = approximate_tokens / workload.target_input_tokens
                self.assertGreater(ratio, 0.9)
                self.assertLess(ratio, 1.1)

    def test_prompts_contain_no_volatile_or_private_material(self):
        volatile = re.compile(
            r"\b20\d\d-\d\d-\d\d\b|https?://|api[_-]?key|\bsk-|password|@gmail",
            re.IGNORECASE,
        )
        for workload in workloads.list_workloads():
            with self.subTest(workload=workload.workload_id):
                self.assertIsNone(volatile.search(workload.prompt))
                self.assertTrue(workload.prompt.isascii())

    def test_workloads_have_distinct_shapes(self):
        sizes = sorted(len(w.prompt) for w in workloads.BENCHMARK_WORKLOADS)
        self.assertGreater(sizes[-1], 10 * sizes[0])
        prompts = {w.prompt for w in workloads.BENCHMARK_WORKLOADS}
        self.assertEqual(len(prompts), len(workloads.BENCHMARK_WORKLOADS))


class OrchestrationTest(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db_path = pathlib.Path(tmp.name) / "x.db"

    def stored(self, request_id):
        request = storage.load_request(self.db_path, request_id)
        self.assertIsNotNone(request)
        return request or {}

    def attempt(self, provider, workload):
        return benchmark.run_attempt(
            provider, workload, "test", self.db_path, origin=ORIGIN
        )

    def test_sends_the_canonical_prompt_and_cap_once_and_stores_the_id(self):
        for workload in workloads.list_workloads():
            with self.subTest(workload=workload.workload_id):
                provider = RecordingProvider()
                request, _, request_id = self.attempt(provider, workload)
                # Exactly one call, with the workload's own content and cap.
                self.assertEqual(
                    provider.calls,
                    [(workload.prompt, workload.max_output_tokens)],
                )
                stored = self.stored(request_id)
                self.assertEqual(stored["workload_id"], workload.workload_id)
                self.assertEqual(
                    stored["requested_max_output_tokens"],
                    workload.max_output_tokens,
                )
                self.assertEqual(request["workload_id"], workload.workload_id)

    def test_provider_reported_tokens_are_the_recorded_facts(self):
        workload = workloads.RAG_V1
        provider = RecordingProvider(input_tokens=15_101, output_tokens=3)
        _, _, request_id = self.attempt(provider, workload)
        stored = self.stored(request_id)
        # Input: the provider's count, not the design target.
        self.assertEqual(stored["input_tokens"], 15_101)
        self.assertNotEqual(
            stored["input_tokens"], workload.target_input_tokens
        )
        # Output: what was generated (3), stored apart from the cap (500); a
        # short answer is a valid result and is not retried or extended.
        self.assertEqual(stored["output_tokens"], 3)
        self.assertEqual(stored["requested_max_output_tokens"], 500)
        self.assertEqual(len(provider.calls), 1)

    def test_failed_attempt_is_not_retried(self):
        provider = providers.DummyProvider(
            first_token_delay_s=0,
            inter_token_delay_s=0,
            fail_with="timeout",
        )
        calls = []
        original = provider.stream

        def counting_stream(prompt, max_output_tokens):
            calls.append(max_output_tokens)
            return original(prompt, max_output_tokens)

        provider.stream = counting_stream
        request, _, _ = self.attempt(provider, workloads.CODING_V1)
        self.assertEqual(request["outcome"], "timeout")
        self.assertEqual(calls, [1_000])

    def test_non_canonical_workload_is_refused_before_any_call(self):
        edited = dataclasses.replace(workloads.RAG_V1, prompt="edited content")
        recapped = dataclasses.replace(workloads.RAG_V1, max_output_tokens=50)
        unknown = dataclasses.replace(
            workloads.RAG_V1, workload_id="rag-v9", version=9
        )
        for workload in (edited, recapped, unknown):
            with self.subTest(workload=workload):
                provider = RecordingProvider()
                with self.assertRaises(ValueError):
                    self.attempt(provider, workload)
                self.assertEqual(provider.calls, [])
                self.assertFalse(self.db_path.exists())

    def test_prompt_is_never_stored(self):
        self.attempt(RecordingProvider(), workloads.CODING_V1)
        stored = self.db_path.read_bytes()
        self.assertNotIn(b"allocate_stock", stored)
        self.assertNotIn(b"warehouse company", stored)


class SafetyAndDependencyTest(unittest.TestCase):

    def test_real_smoke_stays_the_small_fixed_smoke_workload(self):
        self.assertIs(real_smoke.WORKLOAD, workloads.SMOKE_SHORT_TEXT_V2)
        self.assertEqual(real_smoke.WORKLOAD.max_output_tokens, 64)
        self.assertLess(len(real_smoke.WORKLOAD.prompt), 100)
        self.assertEqual(real_smoke.WORKLOAD.category, "smoke")

    def test_workloads_import_nothing_from_the_project_or_third_parties(self):
        tree = ast.parse(
            (REPO_ROOT / "llm_metrics" / "workloads.py").read_text(
                encoding="utf-8"
            )
        )
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module)
        # Standard library only; no providers, storage, analytics, or web.
        self.assertEqual(imported, {"dataclasses", "re"})


if __name__ == "__main__":
    unittest.main()
