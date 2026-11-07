"""Step 027a: question-first home page, pagination, categories, metric Qs."""

# pylint: disable=protected-access

import json
import re
import unittest
from unittest import mock

from llm_metrics import static_site as ss
from tests import test_static_site as t25

STAGING = "https://llmxchange.example.workers.dev"
NEW = (
    "/ttft-vs-total-response-time",
    "/output-tokens-and-llm-response-time",
    "/why-llm-latency-varies",
    "/openai-ttft",
)


# The approved, frozen test copy of the real content (shared helpers).
setUpModule = t25.setUpModule  # pylint: disable=invalid-name
tearDownModule = t25.tearDownModule  # pylint: disable=invalid-name


def published_files(**options):
    """The full test copy: every edition approved and frozen."""
    return ss.render_site(t25.CONFIG, None, t25._PUBLISHED["root"], **options)


def home_links(html: bytes) -> list[str]:
    text = html.decode()
    section = text[text.index('<section id="latest"') :]
    section = section[: section.index("</section>")]
    return re.findall(r'<h2 class="q-title"><a href="(/[^"]+)">', section)


class HomeListTest(unittest.TestCase):

    def test_home_lists_questions_with_summary_category_and_date(self):
        files = published_files()
        links = home_links(files["index.html"])
        self.assertEqual(len(links), 7)
        self.assertEqual(len(set(links)), 7)
        home = files["index.html"].decode()
        self.assertIn('<span class="tag">Performance</span>', home)
        self.assertIn("Published 8 November 2026", home)
        self.assertNotIn(
            "/reports/", home[home.index('<section id="latest"') :]
        )
        self.assertNotIn("page/2/index.html", files)  # no empty pages
        self.assertNotIn('rel="next"', home)

    def test_pagination_without_empty_pages(self):
        with mock.patch.object(ss, "QUESTIONS_PER_PAGE", 4):
            files = published_files()
        first = home_links(files["index.html"])
        second = home_links(files["page/2/index.html"])
        self.assertEqual((len(first), len(second)), (4, 3))
        self.assertFalse(set(first) & set(second))
        self.assertNotIn("page/3/index.html", files)
        self.assertNotIn("page/1/index.html", files)
        page2 = ss.parse_page(files["page/2/index.html"])
        self.assertEqual(page2.links_rel["canonical"], [t25.SITE + "/page/2"])
        text = files["page/2/index.html"].decode()
        self.assertIn('<a rel="prev" href="/">', text)
        self.assertIn('<a rel="next"', files["index.html"].decode())
        self.assertNotIn('rel="next"', text)
        sitemap = files["sitemap.xml"].decode()
        self.assertIn(f"<loc>{t25.SITE}/page/2</loc>", sitemap)
        self.assertNotIn("WebSite", text)  # WebSite markup only on /

    def test_questions_directory_groups_by_category(self):
        directory = published_files()["questions/index.html"].decode()
        self.assertLess(
            directory.index("<h2>Performance</h2>"),
            directory.index("<h2>Reliability</h2>"),
        )
        for path in NEW:
            self.assertIn(f'href="{path}"', directory)

    def test_question_page_layout(self):
        page = published_files()["ttft-vs-total-response-time/index.html"]
        text = page.decode()
        self.assertIn('<p class="eyebrow">Question</p>', text)
        headings = [t for lvl, t in ss.parse_page(page).headings if lvl == 2]
        self.assertEqual(headings[0], "Answer")
        self.assertIn("Related questions", headings)
        self.assertEqual(headings[-1], "About this answer")


class EveryPageIsAQuestionTest(unittest.TestCase):

    def test_every_page_heading_is_a_question(self):
        files = published_files()
        for name, data in files.items():
            if not name.endswith(".html"):
                continue
            headings = ss.parse_page(data).headings
            h1 = next(text for level, text in headings if level == 1)
            self.assertTrue(h1.rstrip().endswith("?"), f"{name}: {h1!r}")


class MetricQuestionTest(unittest.TestCase):

    def test_metric_question_has_no_numbers_without_a_dataset(self):
        page = published_files()["openai-ttft/index.html"]
        text = page.decode()
        self.assertIn("No validated measurements have been published", text)
        self.assertIn('href="/metrics/openai/ttft"', text)
        body = re.sub(r"<[^>]+>", " ", text[text.index("<main") :])
        self.assertIsNone(ss._EMPIRICAL_RE.search(body))


class DraftsAndCategoriesTest(unittest.TestCase):

    def test_new_questions_are_drafts_and_absent_from_staging(self):
        for path in NEW:
            slug = path[1:]
            directory = next(
                p
                for p in (ss.CONTENT_DIR / "questions").iterdir()
                if json.loads((p / "question.json").read_text())["path"] == path
            )
            meta = json.loads((directory / "editions/e1/page.json").read_text())
            self.assertEqual(meta["status"], "draft", slug)
        files = ss.render_site(
            ss.SiteConfig(STAGING),
            preview_at="2026-11-07T20:00:00Z",
            staging=True,
        )
        for path in NEW:
            self.assertNotIn(f"{path[1:]}/index.html", files)
            self.assertFalse(
                any(f'href="{path}"'.encode() in d for d in files.values())
            )
        # A preview shows no publication date: nothing is published yet.
        self.assertNotIn(b"Published ", files["index.html"])

    def test_unknown_category_is_refused(self):
        content = t25.ContentCopy(self)
        path = content.root / "questions/openai-ttft/question.json"
        meta = json.loads(path.read_text())
        meta["category"] = "Speed"
        path.write_text(json.dumps(meta))
        with self.assertRaisesRegex(ss.SiteError, "category"):
            content.render()


if __name__ == "__main__":
    unittest.main()
