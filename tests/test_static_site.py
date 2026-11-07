"""Tests for the static question and metric pages (Steps 025-026). Offline.

Question pages exist only once an edition is published, so most tests
render a temporary copy of `site_content` whose editions were approved and
published (frozen into a temporary archive) at `PUBLISHED_AT`.

Datasets are built by `record_analytics` from the committed synthetic mirror
(`tests/fixtures/gcs_mirror/`), so every number here is synthetic. Nothing
reaches a network, database, GCP or a provider.
"""

import contextlib
import hashlib
import io
import json
import pathlib
import re
import shutil
import tempfile
import unittest

from llm_metrics import record_analytics as ra
from llm_metrics import static_site as ss
from llm_metrics import workloads
from tests import analytics_fixtures as fx
from tests import fakes
from tests.test_record_analytics import population
from tests.test_workloads import PROMPT_SHA256

SITE = "https://llmxchange.com"
QUESTION = "how-to-measure-openai-ttft/index.html"
METRIC = "metrics/openai/ttft/index.html"
DUPLICATE = "prevent-duplicate-paid-llm-api-calls/index.html"
EDITION = "reports/2026-11-08/how-to-measure-openai-ttft/index.html"
DUP_R1 = "reports/2026-11-08/prevent-duplicate-paid-llm-api-calls/index.html"
PAGES = (
    "index.html",
    "llm-performance/index.html",
    "questions/index.html",
    QUESTION,
    DUPLICATE,
    METRIC,
)
CONFIG = ss.SiteConfig(SITE)
PUBLISHED_AT = "2026-11-08T09:00:00Z"
TTFT_EDITION = "questions/how-to-measure-openai-ttft/editions/e1"
_PUBLISHED = {}


def setUpModule():  # pylint: disable=invalid-name
    tmp = pathlib.Path(tempfile.mkdtemp())
    _PUBLISHED["tmp"] = tmp
    root = tmp / "site_content"
    shutil.copytree(ss.CONTENT_DIR, root)
    publish(root)
    _PUBLISHED["root"] = root


def tearDownModule():  # pylint: disable=invalid-name
    shutil.rmtree(_PUBLISHED["tmp"])


def approve_all(root: pathlib.Path) -> None:
    for path in root.glob("questions/*/editions/*/page.json"):
        meta = json.loads(path.read_text())
        meta["status"] = "approved"
        path.write_text(json.dumps(meta))


def publish(root: pathlib.Path, at: str = PUBLISHED_AT) -> list[str]:
    """Approves every edition and freezes the unarchived ones at `at`."""
    approve_all(root)
    _, archive_files, manifest, _ = ss.plan_site(
        CONFIG, None, root, freeze_at=at
    )
    if manifest is not None:
        ss.freeze(root / "archive", archive_files, manifest)
    return sorted(archive_files)


def render(dataset_=None, **options):
    """Renders the published copy of the real content."""
    return ss.render_site(CONFIG, dataset_, _PUBLISHED["root"], **options)


def summary_bytes(policy=True, **overrides) -> bytes:
    return ra.build(
        fx.FIXTURE_ROOT,
        "attempts",
        population(**overrides),
        fx.POLICY_START if policy else None,
    )


def dataset(data=None, source="synthetic") -> ss.Dataset:
    data = summary_bytes() if data is None else data
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "summary.json"
        path.write_bytes(data)
        return ss.load_dataset(path, source, expected_population())


def expected_population():
    _, pages, _ = ss.load_pages()
    return next(p for p in pages if p.kind == "metric").meta[
        "expected_population"
    ]


def section(html_bytes: bytes, section_id: str) -> str:
    text = html_bytes.decode()
    start = text.index(f'<section id="{section_id}">')
    return text[start : text.index("</section>", start)]


def json_ld_blocks(html_bytes: bytes) -> list[dict]:
    return [json.loads(s["text"]) for s in ss.parse_page(html_bytes).scripts]


class ContentCopy:
    """A writable copy of `site_content` for tests that change content."""

    def __init__(self, test: unittest.TestCase):
        tmp = pathlib.Path(tempfile.mkdtemp())
        test.addCleanup(shutil.rmtree, tmp)
        self.root = tmp / "site_content"
        shutil.copytree(ss.CONTENT_DIR, self.root)

    def render(self, dataset_=None):
        """Publishes every edition of this copy, then renders it."""
        publish(self.root)
        return ss.render_site(CONFIG, dataset_, self.root)

    def edit_json(self, page_dir: str, **changes):
        path = self.root / page_dir / "page.json"
        meta = json.loads(path.read_text())
        meta.update(changes)
        path.write_text(json.dumps(meta))

    def write(self, relative: str, text: str):
        (self.root / relative).write_text(text)


class NoDatasetTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.files = render()

    def test_pages_and_assets(self):
        reports = [
            EDITION,
            DUP_R1,
        ]
        self.assertEqual(
            sorted(self.files),
            sorted(
                [
                    *PAGES,
                    *reports,
                    "assets/site.css",
                    "redirects.json",
                    "costs/index.html",
                    "404.html",
                    "sitemap.xml",
                    "robots.txt",
                    "_redirects",
                    "_headers",
                ]
            ),
        )

    def test_unavailable_state_without_numbers(self):
        for name in (QUESTION, METRIC):
            html_text = self.files[name].decode()
            self.assertIn(
                "No validated measurements have been published yet", html_text
            )
            self.assertNotRegex(html_text, r"\d ms\b")
            self.assertNotIn("Synthetic test data", html_text)
        # The empty metric page is noindex; educational pages never are.
        self.assertEqual(
            ss.parse_page(self.files[METRIC]).meta.get("robots"), ["noindex"]
        )
        for name in (QUESTION, DUPLICATE, EDITION, "index.html"):
            self.assertNotIn("noindex", self.files[name].decode())
        self.assertNotIn("<svg", self.files[METRIC].decode())

    def test_render_is_deterministic(self):
        self.assertEqual(render(), self.files)

    def test_head_metadata(self):
        titles = set()
        for name in PAGES:
            parsed = ss.parse_page(self.files[name])
            path = "/" + name.removesuffix("index.html").rstrip("/")
            canonical = SITE + ("/" if path == "/" else path)
            self.assertEqual(parsed.lang, "en")
            self.assertEqual(parsed.meta["charset"], ["utf-8"])
            self.assertEqual(
                parsed.meta["viewport"], ["width=device-width, initial-scale=1"]
            )
            self.assertEqual(parsed.links_rel["canonical"], [canonical])
            self.assertEqual(parsed.meta["og:url"], [canonical])
            self.assertEqual(parsed.meta["og:title"], [parsed.title])
            self.assertEqual(len(parsed.meta["description"]), 1)
            self.assertNotIn("og:image", parsed.meta)
            self.assertEqual([lvl for lvl, _ in parsed.headings].count(1), 1)
            self.assertIn("Content-Security-Policy", parsed.meta)
            titles.add(parsed.title)
        self.assertEqual(len(titles), len(PAGES))

    def test_breadcrumbs_match_json_ld_and_exist(self):
        expected = {
            QUESTION: ["Home", "Questions", "How to measure OpenAI TTFT"],
            EDITION: [
                "Home",
                "Questions",
                "How to measure OpenAI TTFT",
                "8 November 2026 edition",
            ],
            METRIC: ["Home", "LLM Performance", "OpenAI TTFT metrics"],
            "llm-performance/index.html": ["Home", "LLM Performance"],
        }
        for name, names in expected.items():
            parsed = ss.parse_page(self.files[name])
            self.assertEqual([c["name"] for c in parsed.breadcrumb], names)
            (trail,) = [
                b
                for b in json_ld_blocks(self.files[name])
                if b["@type"] == "BreadcrumbList"
            ]
            self.assertEqual(
                [(i["name"], i["item"]) for i in trail["itemListElement"]],
                [
                    (c["name"], CONFIG.absolute(c["path"]))
                    for c in parsed.breadcrumb
                ],
            )
            for crumb in parsed.breadcrumb:
                self.assertTrue(ss._route_exists(crumb["path"], self.files))  # pylint: disable=protected-access
        home = ss.parse_page(self.files["index.html"])
        self.assertEqual(home.breadcrumb, [])

    def test_article_has_no_invented_dates_authors_or_image(self):
        (article,) = [
            b
            for b in json_ld_blocks(self.files[QUESTION])
            if b["@type"] == "Article"
        ]
        self.assertEqual(
            article["headline"],
            "How Do You Measure OpenAI API Time to First Token?",
        )
        self.assertEqual(article["url"], SITE + "/how-to-measure-openai-ttft")
        # The date comes from publication, never from content or build time.
        self.assertEqual(article["datePublished"], PUBLISHED_AT)
        for key in (
            "dateModified",
            "author",
            "publisher",
            "image",
        ):
            self.assertNotIn(key, article)

    def test_cross_links(self):
        question = self.files[QUESTION].decode()
        self.assertIn(
            '<a href="/metrics/openai/ttft">Explore measured OpenAI TTFT</a>',
            question,
        )
        metric = ss.parse_page(self.files[METRIC])
        self.assertIn("/how-to-measure-openai-ttft", metric.hrefs)
        # The metric page does not repeat the article.
        self.assertNotIn(
            "The same request every time", self.files[METRIC].decode()
        )

    def test_every_internal_link_resolves_and_no_scripts_execute(self):
        for name in PAGES:
            parsed = ss.parse_page(self.files[name])
            for href in parsed.hrefs:
                if href.startswith("/"):
                    self.assertTrue(ss._route_exists(href, self.files), href)  # pylint: disable=protected-access
                elif href.startswith("#"):
                    self.assertIn(f'id="{href[1:]}"', self.files[name].decode())
                else:
                    self.assertTrue(href.startswith("https://"), href)
            self.assertTrue(
                all(s["type"] == "application/ld+json" for s in parsed.scripts)
            )
            self.assertNotIn(" style=", self.files[name].decode())

    def test_answer_first_structure(self):
        headings = [
            t
            for lvl, t in ss.parse_page(self.files[QUESTION]).headings
            if lvl == 2
        ]
        self.assertEqual(
            headings,
            [
                "Short answer",
                "What our measurements show",
                "How the measurement works",
                "Exact measurement setup",
                "Limitations",
                "Related pages",
                "Edition history",
            ],
        )


class MethodologyMatchesCodeTest(unittest.TestCase):

    def test_setup_rows_come_from_code(self):
        rows = {row["label"]: row["value"] for row in ss.setup_rows()}
        self.assertEqual(rows["Request profile"], "openai.gpt-6-luna.v1")
        self.assertEqual(rows["Requested output cap"], "300 tokens")
        self.assertEqual(rows["Cache policy"], "disabled")
        self.assertIn("reasoning.effort", rows["Request settings"])
        self.assertEqual(
            rows["Prompt SHA-256"], PROMPT_SHA256["interactive-chat-v1"]
        )
        self.assertEqual(rows["Methodology version"], ss.METHODOLOGY_VERSION)

    def test_article_prose_matches_code_definitions(self):
        directory = ss.CONTENT_DIR / TTFT_EDITION
        prose = " ".join(p.read_text() for p in directory.glob("*.html"))
        workload = workloads.get_workload("interactive-chat-v1")
        self.assertIn(
            f"at most {workload.max_output_tokens} output tokens", prose
        )
        self.assertIn("Lumen Notes", workload.prompt)
        self.assertIn("Lumen Notes", prose)
        for fact in (
            "openai.gpt-6-luna.v1",
            "interactive-chat-v1",
            "us-central1",
            "response.output_text.delta",
            "time.perf_counter()",
        ):
            self.assertIn(fact, prose)
        source = (ss.PACKAGE_DIR / "openai_provider.py").read_text()
        self.assertIn('"response.output_text.delta"', source)
        self.assertIn(
            "time.perf_counter()", (ss.PACKAGE_DIR / "latency.py").read_text()
        )


class DatasetTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = summary_bytes()
        cls.dataset = dataset(cls.data)
        cls.files = render(cls.dataset)

    def test_values_units_provenance_and_copy(self):
        metric = self.files[METRIC].decode()
        for text in (
            "1,650 ms",
            "2,211 ms",
            "83.3% (5 of 6)",
            "108.2 tokens/s",
            "Missing (never ran)",
            ss.METHODOLOGY_VERSION,
            self.dataset.sha256,
            "llm-metrics.analytics.v1",
            "2026-01-05 18:00:00 UTC",
            "$0.000305",
            "Failed: Provider/server error",
        ):
            self.assertIn(text, metric)
        self.assertIn("<svg", metric)
        name = f"data/analytics/{hashlib.sha256(self.data).hexdigest()}.json"
        self.assertEqual(self.files[name], self.data)
        self.assertIn(f'href="/{name}"', metric)

    def test_low_n_is_visible(self):
        for name in (QUESTION, METRIC):
            self.assertIn("Preliminary:", self.files[name].decode())
            self.assertIn("p95 equals the maximum", self.files[name].decode())

    def test_synthetic_data_is_labelled_and_noindex(self):
        for name in PAGES:
            parsed = ss.parse_page(self.files[name])
            self.assertEqual(parsed.meta.get("robots"), ["noindex"])
            self.assertIn("Synthetic test data", self.files[name].decode())
        real = render(dataset(self.data, source="real"))
        self.assertNotIn("noindex", real[METRIC].decode())

    def test_data_refresh_never_changes_the_answer(self):
        without = render()
        for section_id in ("answer", "method", "limitations"):
            self.assertEqual(
                section(self.files[QUESTION], section_id),
                section(without[QUESTION], section_id),
            )
        self.assertIn(
            "how-to-measure-openai-ttft/answer-r1",
            self.files[QUESTION].decode(),
        )
        self.assertIn(
            "Data last refreshed", section(self.files[QUESTION], "findings")
        )

    def test_records_only_dataset_has_no_slot_table(self):
        files = render(dataset(summary_bytes(policy=False)))
        self.assertIn(
            "Slot completeness was not supplied", files[METRIC].decode()
        )

    def test_failures_only_dataset_shows_unknown_not_zero(self):
        data = summary_bytes(
            policy=False,
            start=fx.POLICY_START.replace(minute=30),
            end=fx.POLICY_START.replace(minute=45),
        )
        metric = render(dataset(data))[METRIC].decode()
        self.assertNotIn("<svg", metric)
        self.assertNotRegex(metric, r">0 ms<")
        self.assertIn('<span class="unknown">unknown</span>', metric)
        self.assertIn("0.0% (0 of 1)", metric)


class DatasetRefusalTest(unittest.TestCase):

    def refuse(self, data, message, source="synthetic"):
        with self.assertRaisesRegex(ss.SiteError, message):
            dataset(data, source)

    def reencoded(self, change):
        summary = json.loads(summary_bytes())
        change(summary)
        return ra.encode_summary(summary)

    def test_blank_malformed_and_non_canonical(self):
        self.refuse(b"", "empty")
        self.refuse(b"{nope", "not UTF-8 JSON")
        self.refuse(
            json.dumps(json.loads(summary_bytes()), indent=1).encode(),
            "canonical",
        )
        self.refuse(b'{"a":NaN}', "non-finite")
        self.refuse(b'{"a":1,"a":2}', "duplicate")

    def test_schema_population_and_consistency(self):
        def schema(s):
            s["schema_version"] = "other"

        def region(s):
            s["population"]["origin_region"] = "europe-west1"

        def counts(s):
            s["reliability"]["failures"] = 0

        def ttft(s):
            s["metrics"]["ttft"]["count"] = 4

        def evidence(s):
            s["evidence"]["record_count"] = 99

        def negative(s):
            s["metrics"]["ttft"]["p50"] = -1.0

        for change, message in (
            (schema, "analytics.v1"),
            (region, "population"),
            (counts, "inconsistent"),
            (ttft, "TTFT"),
            (evidence, "evidence"),
            (negative, "non-negative"),
        ):
            self.refuse(self.reencoded(change), message)

    def test_unknown_source_and_symlink(self):
        self.refuse(summary_bytes(), "real or synthetic", source="maybe")
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "s.json"
            target.write_bytes(summary_bytes())
            link = pathlib.Path(tmp) / "link.json"
            link.symlink_to(target)
            with self.assertRaisesRegex(ss.SiteError, "regular file"):
                ss.load_dataset(link, "real", expected_population())


class EscapingTest(unittest.TestCase):

    def test_dataset_strings_are_escaped(self):
        attack = (
            "</script><script>alert(1)</script><img src=x onerror=alert(1)>"
        )
        data = DatasetRefusalTest().reencoded(
            lambda s: s["caveats"].append({"code": "x", "detail": attack})
        )
        files = render(dataset(data))
        metric = files[METRIC].decode()
        self.assertNotIn("<script>alert", metric)
        self.assertNotIn("<img", metric)
        self.assertIn("&lt;/script&gt;&lt;script&gt;alert(1)", metric)

    def test_json_ld_cannot_break_out(self):
        content = ContentCopy(self)
        title = (
            'How do </script><script>alert("x")</script> TTFT & time to'
            " first token?"
        )
        content.edit_json(
            TTFT_EDITION,
            title=title,
            h1=title + " (h1)",
        )
        files = content.render()
        text = files[QUESTION].decode()
        self.assertEqual(text.count("<script"), 2)  # the two JSON-LD blocks
        self.assertNotIn("<script>alert", text)
        self.assertIn("\\u003c/script\\u003e", text)
        (article,) = [
            b
            for b in json_ld_blocks(files[QUESTION])
            if b["@type"] == "Article"
        ]
        self.assertEqual(article["headline"], title)

    def test_unsafe_fragments_are_refused(self):
        for fragment, message in (
            ("<p>x</p><script>alert(1)</script>", "<script>"),
            ('<p onclick="x()">x</p>', "onclick"),
            (
                '<p><a href="javascript:alert(1)">x</a></p>',
                "internal path or https",
            ),
            (
                '<p><a href="http://example.com">x</a></p>',
                "internal path or https",
            ),
            ("<h1>Second</h1>", "<h1>"),
            ('<p style="color:red">x</p>', "style"),
            ("<!-- note --><p>x</p>", "comments"),
        ):
            content = ContentCopy(self)
            content.write(f"{TTFT_EDITION}/answer.html", fragment)
            with self.assertRaisesRegex(ss.SiteError, re.escape(message)):
                content.render()

    def test_broken_internal_link_is_refused(self):
        content = ContentCopy(self)
        content.write(
            f"{TTFT_EDITION}/related.html",
            '<ul><li><a href="/metrics/openai/total-latency">x</a></li></ul>',
        )
        with self.assertRaisesRegex(ss.SiteError, "broken internal link"):
            content.render()


class AnswerMetadataTest(unittest.TestCase):

    def test_known_dates_and_authors_are_rendered(self):
        content = ContentCopy(self)
        content.edit_json(
            TTFT_EDITION,
            authors=[
                {"name": "Example Author", "url": "https://example.com/a"}
            ],
        )
        files = content.render()
        (article,) = [
            b
            for b in json_ld_blocks(files[QUESTION])
            if b["@type"] == "Article"
        ]
        self.assertEqual(article["datePublished"], "2026-11-08T09:00:00Z")
        self.assertNotIn("dateModified", article)  # one edition only
        self.assertEqual(article["author"][0]["name"], "Example Author")
        text = files[QUESTION].decode()
        self.assertIn(
            '<time datetime="2026-11-08T09:00:00Z">8 November 2026</time>', text
        )

    def test_invalid_answer_metadata_is_refused(self):
        for changes, message in (
            ({"answer_basis": "dataset"}, "SHA-256"),
            ({"answer_basis": "guess"}, "answer_basis"),
            ({"date_published": "2026-11-08T09:00:00Z"}, "assigned at"),
            ({"status": "maybe"}, "draft or approved"),
            ({"authors": [{"name": ""}]}, "invalid author"),
            ({"answer_revision": "r1<script>"}, "unsafe"),
        ):
            content = ContentCopy(self)
            content.edit_json(TTFT_EDITION, **changes)
            with self.assertRaisesRegex(ss.SiteError, message):
                ss.load_pages(content.root)

    def test_dataset_based_answers_wait_for_metric_snapshots(self):
        content = ContentCopy(self)
        content.edit_json(
            TTFT_EDITION,
            answer_basis="dataset",
            answer_reviewed_dataset_sha256="a" * 64,
        )
        with self.assertRaisesRegex(ss.SiteError, "metric snapshots"):
            content.render()


class ConfigAndOutputTest(unittest.TestCase):

    def test_site_url_validation(self):
        for url in (
            "http://llmxchange.com",
            "https://llmxchange.com/blog",
            "https://llmxchange.com:8443",
            "https://llmxchange.com/?a=1",
            "https://LLMXCHANGE.com",
            "https://user@llmxchange.com",
            "",
        ):
            with self.assertRaises(ss.SiteError, msg=url):
                ss.SiteConfig(url)
        self.assertEqual(
            ss.SiteConfig("https://llmxchange.com/").absolute("/x"),
            "https://llmxchange.com/x",
        )

    def test_build_replaces_only_previous_builds(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = pathlib.Path(tmp) / "site"
            ss.build(output, SITE)
            first = {
                p: p.read_bytes() for p in output.rglob("*") if p.is_file()
            }
            ss.build(output, SITE)
            second = {
                p: p.read_bytes() for p in output.rglob("*") if p.is_file()
            }
            self.assertEqual(first, second)
            self.assertEqual(sorted(pathlib.Path(tmp).iterdir()), [output])
            other = pathlib.Path(tmp) / "notes"
            other.mkdir()
            (other / "keep.txt").write_text("x")
            with self.assertRaisesRegex(
                ss.SiteError, "not a previous site build"
            ):
                ss.build(other, SITE)
            self.assertEqual((other / "keep.txt").read_text(), "x")
        with self.assertRaisesRegex(
            ss.SiteError, "inside the llm_metrics package"
        ):
            ss.write_site(ss.PACKAGE_DIR / "site_build", {})

    @fakes.no_network
    def test_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = pathlib.Path(tmp) / "summary.json"
            summary.write_bytes(summary_bytes())
            report = pathlib.Path(tmp) / "report.json"
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(
                err
            ):
                code = ss.main(
                    [
                        "--output",
                        f"{tmp}/site",
                        "--site-url",
                        SITE,
                        "--analytics",
                        str(summary),
                        "--data-source",
                        "synthetic",
                        "--report",
                        str(report),
                    ]
                )
            self.assertEqual(code, 0, err.getvalue())
            self.assertIn("Built 6 pages", out.getvalue())
            findings = json.loads(report.read_text())
            self.assertEqual(
                {f["status"] for f in findings} - {"pass", "warn", "manual"},
                set(),
            )
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as exit_:
                    ss.main(
                        [
                            "--output",
                            f"{tmp}/x",
                            "--site-url",
                            SITE,
                            "--analytics",
                            str(summary),
                        ]
                    )
            self.assertEqual(exit_.exception.code, 2)
            summary.write_bytes(b"{}")
            with contextlib.redirect_stderr(io.StringIO()) as err:
                code = ss.main(
                    [
                        "--output",
                        f"{tmp}/y",
                        "--site-url",
                        SITE,
                        "--analytics",
                        str(summary),
                        "--data-source",
                        "real",
                    ]
                )
            self.assertEqual(code, 1)
            self.assertFalse(pathlib.Path(tmp, "y").exists())


class EditorialReportTest(unittest.TestCase):

    def test_report_checks_are_advisory(self):
        files = render()
        _, _, pages = ss.plan_site(CONFIG, None, _PUBLISHED["root"])[1:]
        report = ss.editorial_report(files, pages)
        checks = {f["check"]: f["status"] for f in report}
        for check in (
            "keyphrase in title",
            "keyphrase in h1",
            "keyphrase in meta description",
            "keyphrase in introduction",
            "slug terms",
            "keyphrase density",
            "internal links",
        ):
            self.assertEqual(checks[check], "pass", check)
        self.assertEqual(checks["readability and intent"], "manual")


if __name__ == "__main__":
    unittest.main()
