"""Step 028: weekly publisher, cost editions and the answer-review report.

Offline only: temporary content copies, fixture analytics and synthetic
(labelled) cost ledgers. No network, GCP, Cloudflare, billing or provider.
"""

# pylint: disable=protected-access

import contextlib
import dataclasses
import datetime
import io
import json
import pathlib
import tempfile
import types
import unittest
from unittest import mock

from llm_metrics import cost_ledger
from llm_metrics import static_site as ss
from llm_metrics import weekly_publisher as wp
from tests import analytics_fixtures as fx
from tests import test_site_editions as t26
from tests import test_site_hosting as th
from tests import test_static_site as t25

UTC = datetime.timezone.utc
SITE = t25.SITE
WEEK1 = "2026-11-15T03:00:00Z"  # Sunday after the 02:00 run
WEEK2 = "2026-11-22T03:00:00Z"
COSTS = "/reports/2026-11-15/project-costs"
SNAP1 = "/reports/2026-11-15/openai-ttft-measurements"


def _gate(dataset):
    """Treats the 2-hour fixture as a complete window (tests only)."""
    return dataclasses.replace(
        dataset,
        summary={**dataset.summary, "_published": {"label": "Test window"}},
    )


def synthetic_ledger(**overrides):
    """A synthetic (labelled) ledger, never real billing data."""
    value = th.ledger(reporting_cutoff="2026-11-14T00:00:00Z")
    value["sources"].append(
        {
            "source_id": "weekly-job",
            "vendor": "Google Cloud",
            "service": "Weekly publisher job",
            "category": "weekly_publishing",
            "fully_reconciled": False,
        }
    )
    value.update(overrides)
    return value


class Harness:
    """Content copy, state dir and input files for one test."""

    def __init__(self, test):
        self.test = test
        self.content = t26.Content(test)
        tmp = pathlib.Path(tempfile.mkdtemp())
        test.addCleanup(__import__("shutil").rmtree, tmp)
        self.tmp = tmp
        self.state = tmp / "state"
        self.output = tmp / "site"
        self.config = tmp / "publishing.json"
        self.config.write_text(
            json.dumps(
                {
                    "publishing_enabled": True,
                    "metrics_frequency": "daily",
                    "metrics_run_at_utc": "02:00",
                    "weekly_day": "sunday",
                    "weekly_run_at_utc": "02:00",
                }
            )
        )
        self.ledger_path = tmp / "ledger.json"
        self.write_ledger(synthetic_ledger())
        patcher = mock.patch.object(ss, "production_gate", _gate)
        patcher.start()
        test.addCleanup(patcher.stop)

    def analytics(self, name="a1.json", **overrides) -> pathlib.Path:
        path = self.tmp / name
        path.write_bytes(t25.summary_bytes(**overrides))
        return path

    def write_ledger(self, value):
        self.ledger_path.write_text(json.dumps(value))

    def run(self, now, *extra, analytics=None, ledger=True):
        argv = [
            "--now", now, "--site-url", SITE,
            "--state-dir", str(self.state), "--output", str(self.output),
            "--config", str(self.config),
            "--content-dir", str(self.content.root),
        ]  # fmt: skip
        if analytics is not None:
            argv += ["--analytics", str(analytics)]
        if ledger:
            argv += ["--cost-ledger", str(self.ledger_path)]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = wp.main(argv + list(extra))
        return code, json.loads(out.getvalue())

    def manifest(self):
        return ss.load_manifest(self.content.archive)

    def page(self, name):
        return (self.output / name).read_text("utf-8")


class ScheduleTest(unittest.TestCase):

    def test_latest_sunday_0200_utc(self):
        config = {"weekly_day": "sunday", "weekly_run_at_utc": "02:00"}
        cases = {
            "2026-11-08T02:00:00Z": "2026-11-08T02:00:00Z",
            "2026-11-08T01:59:00Z": "2026-11-01T02:00:00Z",
            "2026-11-11T12:00:00Z": "2026-11-08T02:00:00Z",
            "2026-11-14T23:59:00Z": "2026-11-08T02:00:00Z",
        }
        for now, expected in cases.items():
            with self.subTest(now):
                moment = datetime.datetime.strptime(
                    now, "%Y-%m-%dT%H:%M:%SZ"
                ).replace(tzinfo=UTC)
                self.assertEqual(
                    wp._fmt(wp.latest_week(moment, config)), expected
                )

    def test_bad_schedule_refused(self):
        for config in ({"weekly_day": "sun"}, {"weekly_run_at_utc": "2am"}):
            with self.assertRaises(wp.PublisherError):
                wp.schedule(config)


class WeeklyRunTest(unittest.TestCase):

    def setUp(self):
        self.h = Harness(self)

    def test_first_week_publishes_and_retry_is_a_no_op(self):
        a1 = self.h.analytics()
        code, entry = self.h.run(WEEK1, analytics=a1)
        self.assertEqual(code, 0, entry)
        self.assertEqual(entry["result"], "published")
        self.assertEqual(entry["metrics"]["decision"], "publish")
        self.assertEqual(entry["costs"]["decision"], "publish")
        self.assertIn(SNAP1, entry["published"])
        self.assertIn(COSTS, entry["published"])
        costs = self.h.page("costs/index.html")
        self.assertIn('href="/reports/2026-11-15/project-costs"', costs)
        self.assertIn("Weekly publishing operations", costs)
        self.assertIn("pending reconciliation", costs)
        # Private references and ledger internals never reach the site.
        for path in self.h.output.rglob("*"):
            if path.is_file():
                self.assertNotIn(b"private_reference", path.read_bytes())
        before = self.h.manifest()
        code, again = self.h.run(WEEK1, analytics=a1)
        self.assertEqual((code, again["result"]), (0, "already_done"))
        self.assertEqual(self.h.manifest(), before)

    def test_unchanged_week_keeps_pages_and_adds_nothing(self):
        a1 = self.h.analytics()
        self.h.run(WEEK1, analytics=a1)
        before = self.h.manifest()
        # Re-verified ledger with the same charges: no new cost edition.
        self.h.write_ledger(
            synthetic_ledger(reporting_cutoff="2026-11-21T00:00:00Z")
        )
        code, entry = self.h.run(WEEK2)  # no new analytics this week
        self.assertEqual(code, 0, entry)
        self.assertEqual(entry["metrics"]["decision"], "no_new_data")
        self.assertEqual(entry["costs"]["decision"], "no_change")
        self.assertEqual(entry["result"], "no_change")
        self.assertEqual(self.h.manifest(), before)
        # Metric pages still show the published numbers (accepted copy).
        self.assertIn("Test window", self.h.page(t25.METRIC))

    def test_new_dataset_next_week_adds_one_snapshot(self):
        self.h.run(WEEK1, analytics=self.h.analytics())
        a2 = self.h.analytics(
            "a2.json", end=fx.POLICY_START + datetime.timedelta(hours=1)
        )
        code, entry = self.h.run(WEEK2, analytics=a2)
        self.assertEqual((code, entry["metrics"]["decision"]), (0, "publish"))
        snapshots = self.h.manifest()["metric_snapshots"]
        self.assertEqual(
            [s["route"] for s in snapshots],
            [SNAP1, "/reports/2026-11-22/openai-ttft-measurements"],
        )

    def test_gate_failure_is_held_and_previous_numbers_stay(self):
        self.h.run(WEEK1, analytics=self.h.analytics())
        a2 = self.h.analytics(
            "a2.json", end=fx.POLICY_START + datetime.timedelta(hours=1)
        )
        # Hold: the candidate fails, the accepted dataset is rebuilt.
        calls = {"n": 0}

        def first_fails(dataset):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ss.SiteError("Only 10 successes; at least 50 needed.")
            return _gate(dataset)

        with mock.patch.object(ss, "production_gate", first_fails):
            code, entry = self.h.run(WEEK2, analytics=a2)
        self.assertEqual(code, 0, entry)
        self.assertEqual(entry["metrics"]["decision"], "held")
        self.assertIn("at least 50", entry["metrics"]["reason"])
        self.assertEqual(len(self.h.manifest()["metric_snapshots"]), 1)
        self.assertIn("Test window", self.h.page(t25.METRIC))

    def test_window_after_the_scheduled_run_is_held(self):
        a1 = self.h.analytics()
        # Scheduled run 2026-01-04T02:00Z precedes the fixture window.
        code, entry = self.h.run("2026-01-05T03:00:00Z", analytics=a1)
        self.assertEqual(code, 0, entry)
        self.assertEqual(entry["metrics"]["decision"], "held")
        self.assertIn("after this week's run", entry["metrics"]["reason"])
        self.assertNotIn("metric_snapshots", self.h.manifest())

    def test_modified_cost_edition_is_refused(self):
        self.h.run(WEEK1, analytics=self.h.analytics())
        path = self.h.content.archive / COSTS[1:] / "index.html"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(ss.SiteError, "cost edition was modified"):
            ss.plan_site(t25.CONFIG, None, self.h.content.root)

    def test_stale_ledger_publishes_no_cost_update(self):
        self.h.write_ledger(
            synthetic_ledger(reporting_cutoff="2026-11-01T00:00:00Z")
        )
        code, entry = self.h.run(WEEK1, analytics=self.h.analytics())
        self.assertEqual((code, entry["costs"]["decision"]), (0, "stale"))
        self.assertNotIn(COSTS, entry["published"])
        self.assertIn(
            "Billing evidence is out of date", self.h.page("costs/index.html")
        )

    def test_invalid_ledger_refuses_the_whole_run(self):
        self.h.write_ledger(synthetic_ledger(entries="x"))
        code, entry = self.h.run(WEEK1, analytics=self.h.analytics())
        self.assertEqual((code, entry["result"]), (1, "refused"))
        self.assertFalse(self.h.output.exists())
        self.assertEqual(self.h.manifest()["editions"], [])

    def test_missing_accepted_copy_is_refused(self):
        self.h.run(WEEK1, analytics=self.h.analytics())
        (self.h.state / wp.ACCEPTED_ANALYTICS).unlink()
        code, entry = self.h.run(WEEK2)
        self.assertEqual(code, 1)
        self.assertIn("seed it", entry["reason"])

    def test_dry_run_writes_nothing(self):
        code, entry = self.h.run(WEEK1, "--dry-run",
                                 analytics=self.h.analytics())  # fmt: skip
        self.assertEqual((code, entry["result"]), (0, "dry_run"))
        self.assertIn(COSTS, entry["would_publish"])
        self.assertFalse(self.h.output.exists())
        self.assertFalse((self.h.state / wp.STATE_FILE).exists())
        self.assertFalse(self.h.content.archive.exists())

    def test_disabled_publishing_does_nothing(self):
        self.h.config.write_text(json.dumps({"publishing_enabled": False}))
        code, entry = self.h.run(WEEK1, analytics=self.h.analytics())
        self.assertEqual((code, entry["result"]), (0, "skipped"))
        self.assertFalse(self.h.output.exists())

    def test_review_report_is_written_privately(self):
        self.h.run(WEEK1, analytics=self.h.analytics())
        report = json.loads(
            (self.h.state / "reviews/2026-11-15.json").read_text()
        )
        self.assertTrue(report["rows"])
        self.assertEqual({r["status"] for r in report["rows"]}, {"not_needed"})


def _question(basis, reviewed=None):
    meta = {
        "status": "approved",
        "answer_revision": "x/answer-r1",
        "answer_basis": basis,
        "answer_reviewed_dataset_sha256": reviewed,
    }
    edition = types.SimpleNamespace(page=types.SimpleNamespace(meta=meta))
    return types.SimpleNamespace(
        question_id="q9", path="/x", related_metrics=["/m"], editions=[edition]
    )


class AnswerReviewTest(unittest.TestCase):

    def test_statuses(self):
        new, old = "a" * 64, "b" * 64
        rows = wp.answer_review(
            [
                _question("methodology"),
                _question("dataset", new),
                _question("dataset", old),
            ],
            new,
        )
        self.assertEqual(
            [r["status"] for r in rows],
            ["not_needed", "current", "review_needed"],
        )

    def test_review_needed_holds_metrics(self):
        h = Harness(self)
        with mock.patch.object(
            wp, "answer_review",
            return_value=[{"question_id": "q9", "status": "review_needed"}],
        ):  # fmt: skip
            code, entry = h.run(WEEK1, analytics=h.analytics())
        self.assertEqual(code, 0, entry)
        self.assertEqual(entry["metrics"]["decision"], "held")
        self.assertIn("Answer review needed", entry["metrics"]["reason"])

    def test_committed_answers_need_no_review_now(self):
        _, _, questions = ss.load_pages()
        rows = wp.answer_review(questions, "c" * 64)
        self.assertTrue(rows)
        self.assertEqual({r["status"] for r in rows}, {"not_needed"})


class CostLedgerWeeklyTest(unittest.TestCase):

    def test_content_hash_ignores_timestamps_only(self):
        base = cost_ledger.summarize(synthetic_ledger())
        later = synthetic_ledger(reporting_cutoff="2026-11-20T00:00:00Z")
        for entry in later["entries"]:
            entry["last_verified_at"] = "2026-11-20T00:00:00Z"
        self.assertEqual(
            cost_ledger.summarize(later)["content_sha256"],
            base["content_sha256"],
        )
        changed = synthetic_ledger()
        changed["entries"][0]["charged_amount"] = "11.00"
        self.assertNotEqual(
            cost_ledger.summarize(changed)["content_sha256"],
            base["content_sha256"],
        )

    def test_weekly_publishing_is_separate_and_never_modeled(self):
        summary = cost_ledger.summarize(synthetic_ledger())
        self.assertEqual(
            summary["weekly_publishing"],
            {
                "services": ["Google Cloud Weekly publisher job"],
                "charged": {},
                "status": "pending reconciliation",
            },
        )
        self.assertIsNone(
            cost_ledger.summarize(th.ledger())["weekly_publishing"]
        )

    def test_unknown_category_refused(self):
        value = synthetic_ledger()
        value["sources"][0]["category"] = "misc"
        with self.assertRaises(cost_ledger.LedgerError):
            cost_ledger.validate(value)

    def test_stale(self):
        summary = cost_ledger.summarize(synthetic_ledger())
        self.assertFalse(cost_ledger.stale(summary, "2026-11-22T00:00:00Z"))
        self.assertTrue(cost_ledger.stale(summary, "2026-11-22T00:00:01Z"))


class OutputCheckedBeforeFreezeTest(unittest.TestCase):

    def test_refused_output_leaves_the_archive_untouched(self):
        content = t26.Content(self)
        with tempfile.TemporaryDirectory() as tmp:
            output = pathlib.Path(tmp) / "not-a-build"
            output.mkdir()
            (output / "keep.txt").write_text("x")
            with self.assertRaisesRegex(ss.SiteError, "not a previous"):
                ss.build(
                    output, SITE, content_dir=content.root,
                    freeze_at="2026-11-08T09:00:00Z",
                )  # fmt: skip
        self.assertFalse(content.archive.exists())


if __name__ == "__main__":
    unittest.main()
