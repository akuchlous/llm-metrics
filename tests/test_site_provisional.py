"""Step 027b: provisional real-pilot metrics on a staging preview only."""

# pylint: disable=protected-access

import json
import unittest
from unittest import mock

from llm_metrics import static_site as ss
from tests import test_static_site as t25

STAGING = ss.SiteConfig("https://llmxchange.example.workers.dev")
AT = "2026-11-07T20:00:00Z"


def real(**changes):
    """A real-labelled fixture dataset, optionally with summary changes."""
    data = t25.summary_bytes()
    if changes:
        summary = json.loads(data)
        for path, value in changes.items():
            target = summary
            *parents, key = path.split(".")
            for name in parents:
                target = target[name]
            target[key] = value
        data = ss.record_analytics.encode_summary(summary)
    return t25.dataset(data, source="real")


def clean(dataset_):
    """The fixture with every due slot recorded (the fixture has gaps)."""
    summary = dataset_.summary
    slots = summary["slot_completeness"]
    states = {**slots["states"], "missing": 0, "claim_without_record": 0}
    return ss.Dataset(
        {**summary, "slot_completeness": {**slots, "states": states}},
        dataset_.sha256,
        dataset_.data,
        "real",
    )


def staging(dataset_, **options):
    return ss.render_site(
        STAGING,
        dataset_,
        preview_at=AT,
        staging=True,
        provisional=True,
        **options,
    )


class GateTest(unittest.TestCase):

    def test_needs_staging_and_real_data(self):
        with self.assertRaisesRegex(ss.SiteError, "--staging"):
            ss.render_site(t25.CONFIG, real(), provisional=True)
        with self.assertRaisesRegex(ss.SiteError, "--staging"):
            staging(t25.dataset(source="synthetic"))

    def test_minimum_successes(self):
        dataset_ = clean(real())
        summary = {
            **dataset_.summary,
            "reliability": {
                **dataset_.summary["reliability"],
                "successes": ss.PROVISIONAL_MIN_SUCCESSES - 1,
            },
        }
        low = ss.Dataset(summary, dataset_.sha256, dataset_.data, "real")
        with self.assertRaisesRegex(ss.SiteError, "successes"):
            ss._provisional_gate(low, True, True)

    def test_needs_slot_evidence(self):
        dataset_ = t25.dataset(t25.summary_bytes(policy=False), source="real")
        with self.assertRaisesRegex(ss.SiteError, "slot evidence"):
            ss._provisional_gate(dataset_, True, True)

    def test_too_many_unrecorded_slots(self):
        dataset_ = real()
        slots = dataset_.summary["slot_completeness"]
        summary = {
            **dataset_.summary,
            "reliability": {**dataset_.summary["reliability"], "successes": 99},
            "slot_completeness": {
                **slots,
                "states": {
                    **slots["states"],
                    "missing": slots["expected_slots"],
                },
            },
        }
        broken = ss.Dataset(summary, dataset_.sha256, dataset_.data, "real")
        with self.assertRaisesRegex(ss.SiteError, "no record"):
            ss._provisional_gate(broken, True, True)

    def test_partial_window_is_labelled_and_public_json_allowlisted(self):
        dataset_ = clean(real())
        summary = {
            **dataset_.summary,
            "reliability": {
                **dataset_.summary["reliability"],
                "successes": ss.PROVISIONAL_MIN_SUCCESSES,
            },
            "caveats": dataset_.summary["caveats"]
            + [{"code": "partial_day", "detail": "x"}],
        }
        gated = ss._provisional_gate(
            ss.Dataset(summary, dataset_.sha256, dataset_.data, "real"),
            True,
            True,
        )
        label = gated.summary["_provisional"]["label"]
        self.assertTrue(label.startswith("Partial pilot, as of "))
        self.assertIn("not a 24-hour result or provider-wide benchmark", label)
        self.assertFalse(gated.summary["_provisional"]["complete"])
        public = json.loads(gated.public)
        self.assertNotIn("records", public["evidence"])
        self.assertNotIn("problems", public.get("slot_completeness") or {})
        for metric in public["metrics"].values():
            self.assertNotIn("latest", metric)
        self.assertEqual(
            public["public_projection"]["of_dataset_sha256"], dataset_.sha256
        )
        self.assertNotIn(b"attempts/v1/", gated.public)
        self.assertNotIn(b"attempt_id", gated.public)

    def test_production_path_is_unchanged(self):
        dataset_ = real()
        self.assertIs(ss._provisional_gate(dataset_, False, False), dataset_)


class EvidencePageTest(unittest.TestCase):

    def gated_files(self):
        dataset_ = clean(real())
        # Satisfy the gate with the small fixture.
        with mock.patch.object(ss, "PROVISIONAL_MIN_SUCCESSES", 1):
            return staging(dataset_)

    def test_draft_metric_question_shows_measured_values_only(self):
        files = self.gated_files()
        page = files["openai-ttft/index.html"].decode()
        self.assertIn("Measured values only.", page)
        self.assertIn("not been editorially approved", page)
        self.assertIn("Partial pilot, as of", page)
        self.assertIn('content="noindex, nofollow"', page)
        draft = (
            ss.CONTENT_DIR / "questions/openai-ttft/editions/e1/answer.html"
        ).read_text()
        first_sentence = draft.split("<p>")[1].split(".")[0]
        self.assertNotIn(first_sentence, page)  # no draft prose
        self.assertIn('href="/openai-ttft"', files["index.html"].decode())
        # Other drafts stay out; no dated edition or archive is created.
        self.assertNotIn("ttft-vs-total-response-time/index.html", files)
        self.assertFalse(any(n.startswith("reports/") for n in files))
        json_files = [n for n in files if n.startswith("data/analytics/")]
        self.assertEqual(len(json_files), 1)
        self.assertNotIn(b"attempt_id", files[json_files[0]])

    def test_no_evidence_page_without_provisional_data(self):
        files = ss.render_site(STAGING, preview_at=AT, staging=True)
        self.assertNotIn("openai-ttft/index.html", files)


if __name__ == "__main__":
    unittest.main()
