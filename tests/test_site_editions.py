"""Tests for the question registry and immutable dated editions (Step 026).

Each test works on a temporary copy of `site_content` with its own archive.
Offline only: no network, GCP, database or provider.
"""

import datetime
import json
import pathlib
import re
import shutil
import tempfile
import unittest

from llm_metrics import object_results
from llm_metrics import scheduled_collector as sc
from llm_metrics import static_site as ss
from tests import test_static_site as t25

CONFIG = t25.CONFIG
D1 = "2026-11-08T09:00:00Z"
D2 = "2026-11-10T14:30:00Z"
TTFT = "questions/how-to-measure-openai-ttft"
DUP = "questions/prevent-duplicate-paid-llm-calls"
TTFT_R1 = "reports/2026-11-08/how-to-measure-openai-ttft/index.html"
TTFT_R2 = "reports/2026-11-10/how-to-measure-openai-ttft/index.html"
DUP_R1 = t25.DUP_R1
ROUTE_RE = r"^reports/\d{4}-\d{2}-\d{2}/[a-z0-9-]+(/r\d+)?/index\.html$"


class Content:
    """A writable content copy with its own archive."""

    def __init__(self, test):
        tmp = pathlib.Path(tempfile.mkdtemp())
        test.addCleanup(shutil.rmtree, tmp)
        self.root = tmp / "site_content"
        shutil.copytree(ss.CONTENT_DIR, self.root)
        self.archive = self.root / "archive"

    def meta(self, edition_dir):
        return json.loads((self.root / edition_dir / "page.json").read_text())

    def edit(self, edition_dir, **changes):
        meta = self.meta(edition_dir)
        meta.update(changes)
        (self.root / edition_dir / "page.json").write_text(json.dumps(meta))

    def approve(self, edition_dir):
        self.edit(edition_dir, status="approved")

    def add_edition(self, question, new_id, *, answer, **changes):
        """Copies the last edition, changes its answer, registers it."""
        registry_path = self.root / question / "question.json"
        registry = json.loads(registry_path.read_text())
        source = self.root / question / "editions" / registry["editions"][-1]
        target = self.root / question / "editions" / new_id
        shutil.copytree(source, target)
        (target / "answer.html").write_text(answer)
        meta = json.loads((target / "page.json").read_text())
        meta.update(
            {
                "status": "approved",
                "answer_revision": f"{meta['answer_revision']}-{new_id}",
                "what_changed": "The short answer now explains X.",
                **changes,
            }
        )
        (target / "page.json").write_text(json.dumps(meta))
        registry["editions"].append(new_id)
        registry_path.write_text(json.dumps(registry))

    def publish(self, at, **options):
        files, archive_files, manifest, _ = ss.plan_site(
            CONFIG, None, self.root, freeze_at=at, **options
        )
        if manifest is not None:
            ss.freeze(self.archive, archive_files, manifest)
        return files, sorted(archive_files)

    def render(self, dataset=None, **options):
        return ss.render_site(CONFIG, dataset, self.root, **options)


def hrefs(data):
    return ss.parse_page(data).hrefs


class DefaultContentTest(unittest.TestCase):
    """The committed content: TTFT approved, duplicate-call article draft."""

    def test_nothing_is_published_until_frozen(self):
        files = ss.render_site(CONFIG)
        self.assertFalse(any(name.startswith("reports/") for name in files))
        self.assertNotIn(t25.QUESTION, files)
        home = files["index.html"].decode()
        self.assertIn("No questions have been published yet", home)
        metric = files[t25.METRIC].decode()
        self.assertIn(
            "methodology article for this metric has not been", metric
        )

    def test_publishing_takes_only_approved_editions(self):
        content = Content(self)
        files, archived = content.publish(D1)
        self.assertEqual(archived, [TTFT_R1])
        self.assertIn(t25.QUESTION, files)
        self.assertNotIn(t25.DUPLICATE, files)
        metric = files[t25.METRIC].decode()
        self.assertIn('href="/how-to-measure-openai-ttft"', metric)

    def test_committed_archive_is_consistent(self):
        # Whatever has been published for real must still verify.
        ss.plan_site(CONFIG)


class EditionLifecycleTest(unittest.TestCase):

    def setUp(self):
        self.content = Content(self)
        self.content.approve(f"{DUP}/editions/e1")
        _, archived = self.content.publish(D1)
        self.first = (self.content.archive / TTFT_R1).read_bytes()
        self.content.add_edition(
            TTFT, "e2", answer="<p>A materially revised short answer.</p>"
        )
        _, self.archived_second = self.content.publish(D2)
        self.files = self.content.render()
        self.archived_first = archived

    def test_routes_are_date_first(self):
        self.assertEqual(
            self.archived_first,
            [
                TTFT_R1,
                DUP_R1,
            ],
        )
        self.assertEqual(self.archived_second, [TTFT_R2])
        for name in self.files:
            if name.startswith("reports/"):
                self.assertRegex(
                    name,
                    ROUTE_RE,
                )

    def test_old_edition_bytes_never_change(self):
        self.assertEqual(self.files[TTFT_R1], self.first)
        self.assertEqual(
            (self.content.archive / TTFT_R1).read_bytes(), self.first
        )
        # The old edition does not learn about the new one.
        self.assertNotIn(
            "/reports/2026-11-10/how-to-measure-openai-ttft", hrefs(self.first)
        )
        self.assertIn(
            "/reports/2026-11-08/how-to-measure-openai-ttft",
            hrefs(self.files[TTFT_R2]),
        )

    def test_home_feed_lists_every_edition_newest_first(self):
        home = self.files["index.html"].decode()
        section = home[home.index('<section id="latest">') :]
        order = re.findall(r'href="(/reports/[^"]+)"', section)
        self.assertEqual(
            order,
            [
                "/reports/2026-11-10/how-to-measure-openai-ttft",
                "/reports/2026-11-08/prevent-duplicate-paid-llm-api-calls",
                "/reports/2026-11-08/how-to-measure-openai-ttft",
            ],
        )

    def test_questions_directory_groups_by_identity(self):
        directory = self.files["questions/index.html"].decode()
        self.assertEqual(
            directory.count('<h3><a href="/how-to-measure-openai-ttft">'), 1
        )
        block = directory[
            directory.index('<h3><a href="/how-to-measure-openai-ttft">') :
        ]
        block = block[: block.index("</ul>")]
        self.assertIn("/reports/2026-11-10/how-to-measure-openai-ttft", block)
        self.assertIn("/reports/2026-11-08/how-to-measure-openai-ttft", block)

    def test_hub_shows_latest_answer_history_and_metrics(self):
        hub = self.files[t25.QUESTION].decode()
        self.assertIn("A materially revised short answer.", hub)
        self.assertIn("Answer updated", hub)
        self.assertIn("The short answer now explains X.", hub)
        self.assertIn('href="/metrics/openai/ttft"', hub)
        for route in (
            "/reports/2026-11-10/how-to-measure-openai-ttft",
            "/reports/2026-11-08/how-to-measure-openai-ttft",
        ):
            self.assertIn(f'href="{route}"', hub)
        (article,) = [
            b
            for b in t25.json_ld_blocks(self.files[t25.QUESTION])
            if b["@type"] == "Article"
        ]
        self.assertEqual(
            (article["datePublished"], article["dateModified"]), (D1, D2)
        )

    def test_canonicals(self):
        hub = ss.parse_page(self.files[t25.QUESTION])
        self.assertEqual(
            hub.links_rel["canonical"],
            [t25.SITE + "/how-to-measure-openai-ttft"],
        )
        edition = ss.parse_page(self.files[TTFT_R2])
        self.assertEqual(
            edition.links_rel["canonical"],
            [t25.SITE + "/how-to-measure-openai-ttft"],
        )
        self.assertNotIn(
            "robots", edition.meta
        )  # browseable, not blanket noindex
        self.assertIn("What changed?", self.files[TTFT_R2].decode())
        self.assertIn("Published on", self.files[TTFT_R2].decode())

    def test_no_change_rebuild_publishes_nothing(self):
        manifest = (self.content.archive / ss.MANIFEST_NAME).read_bytes()
        _, archived = self.content.publish("2026-11-12T00:00:00Z")
        self.assertEqual(archived, [])
        self.assertEqual(
            (self.content.archive / ss.MANIFEST_NAME).read_bytes(), manifest
        )
        self.assertEqual(self.content.render(), self.files)

    def test_redirect_plan(self):
        plan = json.loads(self.files["redirects.json"])["redirects"]
        self.assertIn(
            {
                "from": "/how-to-measure-openai-ttft-latest",
                "to": "/how-to-measure-openai-ttft",
                "status": 301,
            },
            plan,
        )
        targets = {rule["to"] for rule in plan}
        self.assertFalse(
            targets & {rule["from"] for rule in plan}
        )  # no chains or loops

    def test_data_refresh_creates_no_edition(self):
        dataset = t25.dataset()
        files, archive_files, manifest, _ = ss.plan_site(
            CONFIG, dataset, self.content.root, freeze_at="2026-11-12T00:00:00Z"
        )
        self.assertEqual((archive_files, manifest), ({}, None))
        self.assertEqual(files[TTFT_R1], self.first)
        self.assertIn("Data last refreshed", files[t25.QUESTION].decode())


class SameDayTest(unittest.TestCase):

    def test_second_same_day_edition_gets_r2(self):
        content = Content(self)
        content.publish(D1)
        content.add_edition(
            TTFT, "e2", answer="<p>Corrected later the same day.</p>"
        )
        _, archived = content.publish("2026-11-08T17:00:00Z")
        self.assertEqual(
            archived,
            ["reports/2026-11-08/how-to-measure-openai-ttft/r2/index.html"],
        )

    def test_utc_date_boundary(self):
        self.assertEqual(
            ss.edition_route("/x", "2026-11-08T23:59:59Z", 1),
            "/reports/2026-11-08/x",
        )
        self.assertEqual(
            ss.edition_route("/x", "2026-11-09T00:00:00Z", 3),
            "/reports/2026-11-09/x/r3",
        )


class RefusalTest(unittest.TestCase):

    def setUp(self):
        self.content = Content(self)
        self.content.publish(D1)

    def assert_refused(self, message, **options):
        with self.assertRaisesRegex(ss.SiteError, message):
            ss.plan_site(CONFIG, None, self.content.root, **options)

    def test_modified_archive_bytes(self):
        path = self.content.archive / TTFT_R1
        path.write_bytes(
            path.read_bytes().replace(b"Short answer", b"Short answr")
        )
        self.assert_refused("was modified")

    def test_edited_published_content(self):
        (self.content.root / TTFT / "editions/e1/answer.html").write_text(
            "<p>Rewritten.</p>"
        )
        self.assert_refused("changed after publication")

    def test_orphaned_archive_file(self):
        stray = self.content.archive / "reports/2026-11-01/old/index.html"
        stray.parent.mkdir(parents=True)
        stray.write_bytes(b"x")
        self.assert_refused("unlisted files")

    def test_other_site_url(self):
        with self.assertRaisesRegex(ss.SiteError, "build with that --site-url"):
            ss.plan_site(
                ss.SiteConfig("https://example.com"), None, self.content.root
            )

    def test_new_edition_rules(self):
        self.content.add_edition(
            TTFT, "e2", answer="<p>New.</p>", what_changed=None
        )
        self.assert_refused("what_changed is required")
        shutil.rmtree(self.content.root / TTFT / "editions/e2")
        registry = json.loads(
            (self.content.root / TTFT / "question.json").read_text()
        )
        registry["editions"].remove("e2")
        (self.content.root / TTFT / "question.json").write_text(
            json.dumps(registry)
        )
        old = self.content.meta(f"{TTFT}/editions/e1")["answer_revision"]
        self.content.add_edition(
            TTFT, "e2", answer="<p>New.</p>", answer_revision=old
        )
        self.assert_refused("new answer_revision")

    def test_publication_must_move_forward(self):
        self.content.add_edition(TTFT, "e2", answer="<p>New.</p>")
        self.assert_refused(
            "after the previous one", freeze_at="2026-11-07T00:00:00Z"
        )
        self.assert_refused("UTC", freeze_at="2026-11-09")

    def test_unverified_empirical_claim(self):
        self.content.add_edition(
            TTFT, "e2", answer="<p>Median TTFT is 1,650 ms.</p>"
        )
        self.assert_refused("states a measured value")

    def test_similar_questions_need_explicit_review(self):
        registry_path = self.content.root / DUP / "question.json"
        meta = self.content.meta(f"{DUP}/editions/e1")
        ttft_h1 = self.content.meta(f"{TTFT}/editions/e1")["h1"]
        self.content.edit(
            f"{DUP}/editions/e1",
            h1=ttft_h1.replace("(TTFT)", "(TTFT) end to end"),
            title=meta["title"],
        )
        self.assert_refused("look like the same question")
        registry = json.loads(registry_path.read_text())
        registry["reviewed_distinct_from"] = ["q0001"]
        registry_path.write_text(json.dumps(registry))
        ss.plan_site(CONFIG, None, self.content.root)

    def test_duplicate_question_id_and_alias_collision(self):
        registry_path = self.content.root / DUP / "question.json"
        registry = json.loads(registry_path.read_text())
        registry_path.write_text(
            json.dumps({**registry, "question_id": "q0001"})
        )
        self.assert_refused("Duplicate question_id")
        registry_path.write_text(
            json.dumps({**registry, "aliases": ["/how-to-measure-openai-ttft"]})
        )
        self.assert_refused("share a path")

    def test_failed_build_keeps_previous_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = pathlib.Path(tmp) / "site"
            ss.build(output, t25.SITE, content_dir=self.content.root)
            before = (output / t25.QUESTION).read_bytes()
            (self.content.root / "pages/questions/intro.html").write_text(
                '<p><a href="/missing">x</a></p>'
            )
            with self.assertRaisesRegex(ss.SiteError, "broken internal link"):
                ss.build(output, t25.SITE, content_dir=self.content.root)
            self.assertEqual((output / t25.QUESTION).read_bytes(), before)

    def test_interrupted_freeze_is_adopted_when_identical(self):
        self.content.add_edition(TTFT, "e2", answer="<p>New.</p>")
        _, archive_files, manifest, _ = ss.plan_site(
            CONFIG, None, self.content.root, freeze_at=D2
        )
        # Simulate a crash after the page was written but before the manifest.
        (self.content.archive / TTFT_R2).parent.mkdir(parents=True)
        (self.content.archive / TTFT_R2).write_bytes(archive_files[TTFT_R2])
        self.assert_refused("unlisted files")
        _, archive_files, manifest, _ = ss.plan_site(
            CONFIG, None, self.content.root, freeze_at=D2
        )
        ss.freeze(self.content.archive, archive_files, manifest)
        ss.plan_site(CONFIG, None, self.content.root)


class PreviewTest(unittest.TestCase):

    def test_preview_shows_drafts_noindex_and_archives_nothing(self):
        content = Content(self)
        files, archive_files, manifest, _ = ss.plan_site(
            CONFIG, None, content.root, preview_at=D1
        )
        self.assertEqual((archive_files, manifest), ({}, None))
        self.assertIn(t25.DUPLICATE, files)
        for name, data in files.items():
            if name.endswith(".html"):
                self.assertEqual(
                    ss.parse_page(data).meta.get("robots"), ["noindex"], name
                )
                self.assertIn("Draft preview", data.decode())
        self.assertFalse(content.archive.exists())
        with self.assertRaisesRegex(ss.SiteError, "never be frozen"):
            ss.plan_site(
                CONFIG, None, content.root, preview_at=D1, freeze_at=D1
            )


class DuplicateCallArticleTest(unittest.TestCase):
    """Facts stated in the duplicate-call article must match the code."""

    def test_facts_match_code(self):
        directory = ss.CONTENT_DIR / DUP / "editions/e1"
        prose = " ".join(p.read_text() for p in directory.glob("*.html"))
        self.assertEqual(sc.SLOT, datetime.timedelta(minutes=15))
        self.assertIn("15-minute", prose)
        self.assertEqual(sc.LATE_LIMIT, datetime.timedelta(minutes=7))
        self.assertIn("more than 7 minutes", prose)
        self.assertEqual(sc.MAX_CLOCK_SKEW, datetime.timedelta(seconds=120))
        self.assertIn("120 seconds", prose)
        self.assertEqual(sc.MAX_SLOTS, 96)
        self.assertIn("exactly 96 slots", prose)
        self.assertEqual(sc.TARGET.profile_id, "openai.gpt-6-luna.v1")
        self.assertEqual(sc.WORKLOAD_ID, "interactive-chat-v1")
        collector = (ss.PACKAGE_DIR / "scheduled_collector.py").read_text()
        self.assertIn('"duplicate_skip"', collector)
        self.assertIn("duplicate_skip", prose)
        store = (ss.PACKAGE_DIR / "object_results.py").read_text()
        self.assertIn("if_generation_match=0", store)
        self.assertIn("ifGenerationMatch=0", prose)
        self.assertEqual(object_results.DEFAULT_MAX_ATTEMPTS, 3)
        repo = ss.PACKAGE_DIR.parent
        # Scheduler retries are cloud configuration, documented in gcloud.md
        # (not shipped in the test image, so checked only when present).
        guide = repo / "gcloud.md"
        if guide.exists():
            self.assertIn("retries: 0", guide.read_text())
        tests = (repo / "tests/test_scheduled_collector.py").read_text()
        self.assertIn("threading.Barrier(8)", tests)
        self.assertIn("self.assertEqual(collector.opener.calls, 96)", tests)
        # It states limits, not guarantees.
        self.assertIn(
            "What these controls do not guarantee",
            (directory / "page.json").read_text(),
        )


if __name__ == "__main__":
    unittest.main()
