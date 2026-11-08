"""Tests for Step 027: costs page, hosting files, route emulation, runner.

Offline only: no Cloudflare, GCP, network or provider access. Ledger and
dataset values are synthetic.
"""

import contextlib
import datetime
import io
import json
import pathlib
import re
import shutil
import tempfile
import unittest
from unittest import mock

from llm_metrics import cost_ledger
from llm_metrics import publish_runner as pr
from llm_metrics import static_site as ss
from tests import test_site_editions as t26
from tests import test_static_site as t25

CONFIG = t25.CONFIG


def setUpModule():  # pylint: disable=invalid-name
    t25.setUpModule()


def tearDownModule():  # pylint: disable=invalid-name
    t25.tearDownModule()


SHA = "ab" * 32
UTC = datetime.timezone.utc


def ledger(**overrides):
    value = {
        "schema_version": "llm-metrics.cost-ledger.v1",
        "project_start": "2026-10-28",
        "reporting_cutoff": "2026-11-07T00:00:00Z",
        "sources": [
            {
                "source_id": "openai-api",
                "vendor": "OpenAI",
                "service": "API",
                "fully_reconciled": True,
                "reconciliation_method": "invoice",
                "reconciled_through": "2026-11-07",
            },
            {
                "source_id": "gcp",
                "vendor": "Google Cloud",
                "service": "Billing account",
                "fully_reconciled": False,
            },
        ],
        "entries": [
            entry("e1", "openai-api", "10.00", refunds="0.50"),
            entry("e2", "gcp", "1.20", currency="EUR", sha="cd" * 32),
            entry(
                "e3",
                "gcp",
                "0.30",
                status="estimate",
                sha="ef" * 32,
                start="2026-11-01",
                end="2026-11-05",
            ),
        ],
    }
    value.update(overrides)
    return value


def entry(
    entry_id,
    source,
    amount,
    *,
    status="charged",
    currency="USD",
    sha=SHA,
    start="2026-10-28",
    end="2026-11-06",
    **extra,
):
    return {
        "entry_id": entry_id,
        "source_id": source,
        "status": status,
        "currency": currency,
        "period_start": start,
        "period_end": end,
        "charged_amount": amount,
        "evidence_description": "Monthly invoice PDF",
        "evidence_sha256": sha,
        "last_verified_at": "2026-11-07T08:00:00Z",
        "private_reference": f"INV-SECRET-{entry_id}",
        **extra,
    }


class CostLedgerTest(unittest.TestCase):

    def test_partial_ledger_shows_subtotal_not_lifetime_total(self):
        summary = cost_ledger.summarize(ledger())
        self.assertIsNone(summary["lifetime_total"])
        self.assertEqual(
            summary["lifetime_status"], cost_ledger.LIFETIME_UNVERIFIED
        )
        # Per currency, refunds deducted, estimates never added.
        self.assertEqual(
            summary["verified_charged_subtotal"], {"EUR": "1.20", "USD": "9.50"}
        )
        self.assertEqual(
            summary["unverified_sources"], ["Google Cloud Billing account"]
        )
        self.assertNotIn("INV-SECRET", json.dumps(summary))

    def test_lifetime_total_only_when_everything_is_reconciled(self):
        complete = ledger(
            sources=[ledger()["sources"][0]],
            entries=[entry("e1", "openai-api", "10.00")],
        )
        summary = cost_ledger.summarize(complete)
        self.assertEqual(summary["lifetime_total"], {"USD": "10.00"})
        unpaid = ledger(
            sources=[ledger()["sources"][0]],
            entries=[
                entry("e1", "openai-api", "10.00"),
                entry(
                    "e2",
                    "openai-api",
                    "2.00",
                    status="invoiced_unpaid",
                    sha="cd" * 32,
                    start="2026-11-07",
                    end="2026-11-07",
                ),
            ],
        )
        summary = cost_ledger.summarize(unpaid)
        self.assertIsNone(summary["lifetime_total"])
        self.assertEqual(summary["invoiced_unpaid"], {"USD": "2.00"})

    def test_source_without_bills_is_unknown_not_zero(self):
        summary = cost_ledger.summarize(ledger(entries=[]))
        self.assertEqual(summary["verified_charged_subtotal"], {})
        # A reconciled source with no bills was charged nothing; an
        # unreconciled one without bills is unknown.
        self.assertEqual(
            [r["status"] for r in summary["sources"]],
            ["reconciled", "no billing records"],
        )
        self.assertIsNone(summary["lifetime_total"])

    def test_refusals(self):
        cases = (
            (
                dict(
                    entries=[
                        entry("e1", "openai-api", "1.00"),
                        entry("e2", "openai-api", "2.00", sha="cd" * 32),
                    ]
                ),
                "overlaps",
            ),
            (
                dict(
                    entries=[
                        entry("e1", "openai-api", "1.00"),
                        entry("e2", "gcp", "2.00"),
                    ]
                ),
                "evidence already used",
            ),
            (
                dict(
                    entries=[
                        entry("e1", "openai-api", "1.00"),
                        entry("e1", "gcp", "2.00", sha="cd" * 32),
                    ]
                ),
                "duplicate entry",
            ),
            (dict(entries=[entry("e1", "openai-api", "-1")]), "decimal string"),
            (
                dict(entries=[entry("e1", "openai-api", "1", currency="usd")]),
                "ISO 4217",
            ),
            (dict(entries=[entry("e1", "nope", "1")]), "unknown source"),
            (
                dict(entries=[entry("e1", "openai-api", "1", refunds="2")]),
                "refunds exceed",
            ),
            (
                dict(
                    entries=[entry("e1", "openai-api", "1", start="2026-01-01")]
                ),
                "before start",
            ),
            (dict(schema_version="x"), "cost-ledger.v1"),
        )
        for overrides, message in cases:
            with self.assertRaisesRegex(cost_ledger.LedgerError, message):
                cost_ledger.validate(ledger(**overrides))


class CostsPageTest(unittest.TestCase):

    def test_no_ledger_is_honest_and_noindex(self):
        files = ss.render_site(CONFIG)
        page = files["costs/index.html"].decode()
        self.assertIn("No verified billing data has been published yet", page)
        self.assertEqual(
            ss.parse_page(files["costs/index.html"]).meta["robots"], ["noindex"]
        )
        self.assertNotIn("/costs", files["sitemap.xml"].decode())

    def test_partial_ledger_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "ledger.json"
            path.write_text(json.dumps(ledger()))
            files, _, _ = ss.build(
                pathlib.Path(tmp) / "site", t25.SITE, cost_ledger_path=path
            )
        page = files["costs/index.html"].decode()
        self.assertIn("Full lifetime total not yet verified.", page)
        self.assertIn("USD 9.50", page)
        self.assertIn("EUR 1.20", page)
        self.assertIn("Not yet verified: Google Cloud Billing account", page)
        # The estimate is listed only as planned, never in a charged total.
        charged, planned = page.split("Planned costs", 1)
        self.assertNotIn("0.30", charged)
        self.assertIn("USD 0.30", planned.split("Status by service")[0])
        self.assertIn("Every charge so far", page)
        self.assertIn("Total charged (USD)", page)
        self.assertIn("<strong>USD 9.50</strong>", page)
        self.assertIn("<strong>EUR 1.20</strong>", page)
        self.assertNotIn("noindex", page)
        for data in files.values():
            self.assertNotIn(b"INV-SECRET", data)
        self.assertIn(
            "https://llmxchange.com/costs", files["sitemap.xml"].decode()
        )

    def test_line_items_and_planned_are_separate(self):
        summary = cost_ledger.summarize(ledger())
        self.assertEqual(
            [(i["vendor"], i["amount"], i["status"])
             for i in summary["line_items"]],
            [
                ("OpenAI", "9.50", "charged"),
                ("Google Cloud", "1.20", "charged"),
            ],
        )  # fmt: skip
        self.assertEqual(
            [(i["service"], i["amount"]) for i in summary["planned"]],
            [("Billing account", "0.30")],
        )
        self.assertEqual(
            summary["verified_charged_subtotal"], {"EUR": "1.20", "USD": "9.50"}
        )

    def test_private_reference_in_content_is_refused(self):
        content = t25.ContentCopy(self)
        content.write("pages/costs/answer.html", "<p>See INV-SECRET-e1.</p>")
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "ledger.json"
            path.write_text(json.dumps(ledger()))
            with self.assertRaisesRegex(ss.SiteError, "Forbidden content"):
                ss.build(
                    pathlib.Path(tmp) / "site",
                    t25.SITE,
                    content_dir=content.root,
                    cost_ledger_path=path,
                )


class HostingFilesTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.files = t25.render()

    def test_sitemap_lists_only_indexable_canonical_pages(self):
        sitemap = self.files["sitemap.xml"].decode()
        locs = re.findall(r"<loc>([^<]+)</loc>", sitemap)
        self.assertEqual(
            locs,
            sorted(
                [
                    "https://llmxchange.com/",
                    "https://llmxchange.com/how-to-measure-openai-ttft",
                    "https://llmxchange.com/llm-performance",
                    t25.SITE + "/prevent-duplicate-paid-llm-api-calls",
                    "https://llmxchange.com/questions",
                    *(
                        t25.SITE + "/" + p.split("/", maxsplit=1)[0]
                        for p in t25.NEW_QUESTIONS
                    ),
                ]
            ),
        )
        self.assertNotIn("/reports/", sitemap)
        self.assertNotIn("-latest", sitemap)
        self.assertNotIn("/metrics/openai/ttft", sitemap)  # noindex, no data
        self.assertIn(
            "<loc>https://llmxchange.com/how-to-measure-openai-ttft</loc>"
            f"<lastmod>{t25.PUBLISHED_AT}</lastmod>",
            sitemap,
        )
        self.assertIn(
            "<loc>https://llmxchange.com/llm-performance</loc></url>", sitemap
        )

    def test_sitemap_is_stable_across_rebuilds(self):
        self.assertEqual(t25.render()["sitemap.xml"], self.files["sitemap.xml"])

    def test_robots_headers_redirects_and_404(self):
        self.assertEqual(
            self.files["robots.txt"].decode(),
            "User-agent: *\nAllow: /\n\n"
            "Sitemap: https://llmxchange.com/sitemap.xml\n",
        )
        headers = self.files["_headers"].decode()
        self.assertIn(
            f"Content-Security-Policy: {ss.CSP}; frame-ancestors 'none'",
            headers,
        )
        self.assertIn("X-Content-Type-Options: nosniff", headers)
        self.assertIn(
            "/how-to-measure-openai-ttft-latest"
            " /how-to-measure-openai-ttft 301\n",
            self.files["_redirects"].decode(),
        )
        not_found = ss.parse_page(self.files["404.html"])
        self.assertEqual(not_found.meta["robots"], ["noindex, nofollow"])
        self.assertNotIn("canonical", not_found.links_rel)

    def test_cloudflare_route_emulation(self):
        files = self.files
        for path, expected in (
            ("/", (200, "index.html")),
            (
                "/how-to-measure-openai-ttft",
                (200, "how-to-measure-openai-ttft/index.html"),
            ),
            (
                "/how-to-measure-openai-ttft/",
                (307, "/how-to-measure-openai-ttft"),
            ),
            (
                "/how-to-measure-openai-ttft/index.html",
                (307, "/how-to-measure-openai-ttft"),
            ),
            (
                "/reports/2026-11-08/how-to-measure-openai-ttft",
                (
                    200,
                    "reports/2026-11-08/how-to-measure-openai-ttft/index.html",
                ),
            ),
            (
                "/how-to-measure-openai-ttft-latest",
                (301, "/how-to-measure-openai-ttft"),
            ),
            ("/assets/site.css", (200, "assets/site.css")),
            ("/sitemap.xml", (200, "sitemap.xml")),
            ("/_headers", (404, "404.html")),
            ("/no-such-page", (404, "404.html")),
        ):
            self.assertEqual(ss.resolve(files, path), expected, path)

    def test_every_link_resolves_through_the_host_emulation(self):
        for name, data in self.files.items():
            if not name.endswith(".html"):
                continue
            for href in ss.parse_page(data).hrefs:
                if href.startswith("/"):
                    self.assertEqual(
                        ss.resolve(self.files, href)[0], 200, (name, href)
                    )

    def test_navigation_and_accessibility_basics(self):
        home = self.files["index.html"].decode()
        self.assertIn('<a class="skip-link" href="#content">', home)
        self.assertIn('<main id="content">', home)
        self.assertIn('<nav aria-label="Main"', home)
        for label in ("Questions", "Metrics", "Costs"):
            self.assertIn(f">{label}</a>", home)
        css = (ss.PACKAGE_DIR / "site_static/site.css").read_text()
        self.assertIn(":focus-visible", css)
        self.assertIn("prefers-color-scheme: dark", css)
        self.assertNotIn("@import", css)
        self.assertNotIn("url(http", css)
        self.assertLess(len(css.encode()), 20_000)

    def test_forbidden_content_scan(self):
        with self.assertRaisesRegex(ss.SiteError, "Forbidden"):
            ss.scan_public({"x.html": b"see gs://llm-metrics-513617-results/x"})
        with self.assertRaisesRegex(ss.SiteError, "request id"):
            ss.scan_public({"x.html": b"req_abcdef123456"})
        ss.scan_public(self.files)

    def test_wrangler_config(self):
        path = ss.PACKAGE_DIR.parent / "wrangler.jsonc"
        if not path.exists():
            self.skipTest("wrangler.jsonc is not in the test image")
        text = path.read_text()
        config = json.loads(re.sub(r"^\s*//.*$", "", text, flags=re.M))
        self.assertNotIn(
            "main", config
        )  # assets only: nothing billed per request
        self.assertEqual(
            config["assets"],
            {
                "directory": "./site_build",
                "html_handling": "drop-trailing-slash",
                "not_found_handling": "404-page",
            },
        )


class StagingTest(unittest.TestCase):

    def test_preview_build_is_not_indexable_on_any_hostname(self):
        host = "https://llmxchange.example.workers.dev"
        content = t26.Content(self)
        files = ss.render_site(
            ss.SiteConfig(host), None, content.root, preview_at=t26.D1
        )
        headers = files["_headers"].decode()
        self.assertIn("X-Robots-Tag: noindex, nofollow", headers)
        self.assertNotIn("Sitemap:", files["robots.txt"].decode())
        self.assertNotIn("<loc>", files["sitemap.xml"].decode())
        home = ss.parse_page(files["index.html"])
        self.assertEqual(home.meta["robots"], ["noindex, nofollow"])
        self.assertEqual(home.links_rel["canonical"], [host + "/"])
        self.assertNotIn(b"https://llmxchange.com", files["index.html"])
        self.assertFalse(content.archive.exists())
        production = ss.render_site(CONFIG)["_headers"].decode()
        self.assertNotIn("X-Robots-Tag", production)

    def test_staging_build_has_approved_answers_only_and_no_editions(self):
        host = "https://llmxchange.example.workers.dev"
        files = ss.render_site(
            ss.SiteConfig(host),
            preview_at="2026-11-07T20:00:00Z",
            staging=True,
        )
        self.assertFalse(any(n.startswith("reports/") for n in files))
        self.assertIn("how-to-measure-openai-ttft/index.html", files)
        self.assertIn("openai-ttft/index.html", files)  # approved 2026-11-08
        for name, data in files.items():
            if name.endswith(".html"):
                self.assertEqual(
                    ss.parse_page(data).meta["robots"],
                    ["noindex, nofollow"],
                    name,
                )
        self.assertIn(b"Staging preview", files["index.html"])
        # A staging build never adds to the production archive.
        archive = ss.CONTENT_DIR / "archive"
        before = sorted(archive.rglob("*")) if archive.exists() else []
        ss.render_site(
            ss.SiteConfig("https://llmxchange.example.workers.dev"),
            preview_at="2026-11-07T20:00:00Z",
            staging=True,
        )
        after = sorted(archive.rglob("*")) if archive.exists() else []
        self.assertEqual(before, after)

    def test_staging_needs_a_preview_time(self):
        with self.assertRaises(ss.SiteError):
            ss.render_site(CONFIG, staging=True)


class ScheduleTest(unittest.TestCase):

    def config(self, frequency):
        return {
            "publishing_enabled": True,
            "metrics_frequency": frequency,
            "metrics_run_at_utc": "02:00",
        }

    def at(self, text):
        return pr.parse_utc(text)

    def test_daily(self):
        config = self.config("daily")
        self.assertEqual(
            pr.latest_scheduled(self.at("2026-11-08T01:59:59Z"), config),
            self.at("2026-11-07T02:00:00Z"),
        )
        self.assertEqual(
            pr.latest_scheduled(self.at("2026-11-08T02:00:00Z"), config),
            self.at("2026-11-08T02:00:00Z"),
        )

    def test_every_three_days_and_weekly(self):
        three = self.config("every_3_days")
        # Anchored at 2026-01-05, so slots fall on 2026-11-07, -10, ...
        self.assertEqual(
            pr.latest_scheduled(self.at("2026-11-09T12:00:00Z"), three),
            self.at("2026-11-07T02:00:00Z"),
        )
        weekly = self.config("weekly")
        self.assertEqual(
            pr.latest_scheduled(self.at("2026-11-08T12:00:00Z"), weekly),
            self.at("2026-11-02T02:00:00Z"),
        )  # a Monday
        self.assertEqual(self.at("2026-11-02T02:00:00Z").weekday(), 0)

    def test_invalid_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "p.json"
            for bad in (
                {
                    "publishing_enabled": "yes",
                    "metrics_frequency": "daily",
                    "metrics_run_at_utc": "02:00",
                },
                {
                    "publishing_enabled": True,
                    "metrics_frequency": "hourly",
                    "metrics_run_at_utc": "02:00",
                },
                {
                    "publishing_enabled": True,
                    "metrics_frequency": "daily",
                    "metrics_run_at_utc": "25:00",
                },
            ):
                path.write_text(json.dumps(bad))
                with self.assertRaises(pr.RunnerError):
                    pr.load_config(path)


class RunnerTest(unittest.TestCase):

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.content = t26.Content(self)
        self.state = self.tmp / "state"
        self.output = self.tmp / "site"
        self.config = self.tmp / "publishing.json"
        self.set_config()
        self.summary = self.tmp / "summary.json"
        self.summary.write_bytes(t25.summary_bytes())
        # These tests cover the lane logic with the 2-hour fixture; the
        # Step 028 production thresholds are tested in ProductionGateTest.
        patcher = mock.patch.object(ss, "production_gate", lambda d: d)
        patcher.start()
        self.addCleanup(patcher.stop)

    def set_config(self, **changes):
        config = {
            "publishing_enabled": True,
            "metrics_frequency": "daily",
            "metrics_run_at_utc": "02:00",
            **changes,
        }
        self.config.write_text(json.dumps(config))

    def run_lane(self, lane, *extra):
        args = [
            lane,
            "--output",
            str(self.output),
            "--site-url",
            t25.SITE,
            "--state-dir",
            str(self.state),
            "--config",
            str(self.config),
            "--content-dir",
            str(self.content.root),
            *extra,
        ]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = pr.main(args)
        return code, json.loads(out.getvalue())

    def metrics(self, now, *extra, source="real"):
        return self.run_lane(
            "metrics",
            "--now",
            now,
            "--analytics",
            str(self.summary),
            "--data-source",
            source,
            *extra,
        )

    def test_editorial_release_without_any_dataset(self):
        code, result = self.run_lane("editorial", "--publish-at", t26.D1)
        self.assertEqual((code, result["result"]), (0, "published"))
        self.assertIn(
            "/reports/2026-11-08/how-to-measure-openai-ttft",
            result["published"],
        )
        self.assertTrue((self.output / t25.QUESTION).is_file())
        code, result = self.run_lane(
            "editorial", "--publish-at", "2026-11-09T09:00:00Z"
        )
        self.assertEqual(result["result"], "no_change")

    def test_metrics_lane_gates(self):
        code, result = self.metrics("2026-11-08T02:05:00Z", source="synthetic")
        self.assertEqual((code, result["result"]), (1, "refused"))
        code, result = self.metrics("2026-11-08T02:05:00Z")
        self.assertIn("less than 24 hours", result["reason"])  # fixture is 2 h
        self.assertFalse(self.output.exists())
        code, result = self.metrics(
            "2026-11-08T02:05:00Z", "--allow-preliminary"
        )
        self.assertEqual((code, result["result"]), (0, "published"))
        page = (self.output / t25.METRIC).read_bytes()
        self.assertNotIn(b"noindex", page)
        # Same day again: not due. Next day, same data: unchanged, no rebuild.
        self.assertEqual(
            self.metrics("2026-11-08T20:00:00Z", "--allow-preliminary")[1][
                "reason"
            ],
            "not_due",
        )
        self.assertEqual(
            self.metrics("2026-11-09T02:01:00Z", "--allow-preliminary")[1][
                "reason"
            ],
            "unchanged_dataset",
        )
        history = (self.state / "history.jsonl").read_text().splitlines()
        self.assertEqual(len(history), 5)

    def test_metrics_failure_does_not_block_editorial(self):
        self.metrics("2026-11-08T02:05:00Z", "--allow-preliminary")
        before = (self.output / t25.METRIC).read_bytes()
        self.summary.write_bytes(b"{broken")
        code, result = self.metrics("2026-11-09T02:05:00Z")
        self.assertEqual((code, result["result"]), (1, "refused"))
        self.assertEqual((self.output / t25.METRIC).read_bytes(), before)
        code, result = self.run_lane(
            "editorial", "--publish-at", "2026-11-09T09:00:00Z"
        )
        self.assertEqual(code, 0)
        # The editorial release kept the previously accepted metrics.
        self.assertIn(b"1,650 ms", (self.output / t25.METRIC).read_bytes())
        self.assertTrue((self.output / t25.QUESTION).is_file())

    def test_current_day_window_is_refused(self):
        _, result = self.metrics("2026-01-05T21:00:00Z", "--allow-preliminary")
        self.assertIn("current UTC day", result["reason"])

    def test_emergency_switch_and_dry_run(self):
        self.set_config(publishing_enabled=False)
        code, result = self.run_lane("editorial", "--publish-at", t26.D1)
        self.assertEqual((code, result["reason"]), (0, "publishing_disabled"))
        self.assertFalse(self.output.exists())
        self.set_config()
        code, result = self.run_lane(
            "editorial", "--publish-at", t26.D1, "--dry-run"
        )
        self.assertEqual(result["result"], "dry_run")
        self.assertIn(
            "reports/2026-11-08/how-to-measure-openai-ttft/index.html",
            result["would_publish"],
        )
        self.assertFalse(self.output.exists())
        self.assertFalse(self.content.archive.exists())

    def test_tampered_accepted_dataset_is_refused(self):
        self.metrics("2026-11-08T02:05:00Z", "--allow-preliminary")
        (self.state / pr.ACCEPTED_DATASET).write_bytes(b"{}")
        code, result = self.run_lane("editorial", "--publish-at", t26.D1)
        self.assertEqual(code, 1)
        self.assertIn("missing or changed", result["reason"])


class ProductionGateTest(unittest.TestCase):
    """Step 028: real numbers reach production only past the thresholds."""

    def gated(self, **summary_changes):
        dataset = t25.dataset(t25.summary_bytes(), source="real")
        summary = {**dataset.summary, **summary_changes}
        return ss.Dataset(summary, dataset.sha256, dataset.data, "real")

    def complete(self, successes=60, missing=0):
        dataset = self.gated()
        slots = dataset.summary["slot_completeness"]
        if successes is None:
            successes = dataset.summary["reliability"]["successes"]
        return self.gated(
            caveats=[
                c for c in dataset.summary["caveats"]
                if c["code"] != "partial_day"
            ],
            reliability={
                **dataset.summary["reliability"], "successes": successes,
            },
            slot_completeness={
                **slots,
                "expected_slots": slots["policy"]["max_slots"],
                "states": {**slots["states"], "missing": missing,
                           "claim_without_record": 0},
            },
        )  # fmt: skip

    def test_partial_window_is_refused_even_with_allow_preliminary(self):
        with self.assertRaisesRegex(ss.SiteError, "complete 24-hour"):
            ss.production_gate(self.gated())

    def test_thresholds(self):
        gated = ss.production_gate(self.complete())
        self.assertIn(
            "Complete 24-hour pilot", gated.summary["_published"]["label"]
        )
        with self.assertRaisesRegex(ss.SiteError, "successes"):
            ss.production_gate(self.complete(successes=49))
        with self.assertRaisesRegex(ss.SiteError, "no record"):
            ss.production_gate(self.complete(missing=5))

    def test_build_applies_the_gate_to_real_production_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "summary.json"
            path.write_bytes(t25.summary_bytes())
            with self.assertRaisesRegex(ss.SiteError, "complete 24-hour"):
                ss.build(pathlib.Path(tmp) / "site", t25.SITE, path, "real")


class MetricSnapshotTest(unittest.TestCase):
    """Step 028: dated immutable metric snapshots."""

    def setUp(self):
        self.content = t26.Content(self)
        # The fixture's real counts (plan_site re-validates them), with the
        # success threshold lowered for this test only.
        patcher = mock.patch.object(ss, "PRODUCTION_MIN_SUCCESSES", 1)
        patcher.start()
        self.addCleanup(patcher.stop)
        dataset = ProductionGateTest().complete(successes=None)
        self.dataset = ss.production_gate(dataset)

    def plan(self, at=None, dataset=None):
        return ss.plan_site(
            CONFIG, dataset or self.dataset, self.content.root, freeze_at=at
        )

    def freeze(self, at):
        files, archive_files, manifest, _ = self.plan(at)
        if manifest is not None:  # as build() does
            ss.freeze(self.content.archive, archive_files, manifest)
        return files, archive_files

    def test_snapshot_is_created_once_and_served_verbatim(self):
        files, archived = self.freeze("2026-11-08T07:00:00Z")
        route = "reports/2026-11-08/openai-ttft-measurements/index.html"
        self.assertIn(route, archived)
        page = ss.parse_page(files[route])
        self.assertEqual(
            page.links_rel["canonical"], [t25.SITE + "/metrics/openai/ttft"]
        )
        self.assertNotIn(
            route.split("/index", maxsplit=1)[0], files["sitemap.xml"].decode()
        )
        metric = files[t25.METRIC].decode()
        self.assertIn(f'href="/{route[:-11]}"', metric)
        self.assertIn("Complete 24-hour pilot", metric)
        # Same dataset again: no new snapshot; archived bytes reused.
        files2, archived2 = self.freeze("2026-11-08T08:00:00Z")
        self.assertEqual([n for n in archived2 if "measurements" in n], [])
        self.assertEqual(files2[route], files[route])
        manifest = json.loads(
            (self.content.archive / ss.MANIFEST_NAME).read_text()
        )
        self.assertEqual(len(manifest["metric_snapshots"]), 1)

    def test_modified_snapshot_is_refused(self):
        self.freeze("2026-11-08T07:00:00Z")
        path = (
            self.content.archive
            / "reports/2026-11-08/openai-ttft-measurements/index.html"
        )
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(ss.SiteError, "snapshot was modified"):
            self.plan()

    def test_staging_never_creates_snapshots(self):
        _, archived, manifest, _ = ss.plan_site(
            ss.SiteConfig("https://llmxchange.example.workers.dev"),
            self.dataset,
            self.content.root,
            preview_at="2026-11-08T07:00:00Z",
            staging=True,
        )
        self.assertEqual(archived, {})
        self.assertIsNone(manifest)


if __name__ == "__main__":
    unittest.main()
