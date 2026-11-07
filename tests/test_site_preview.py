"""Local site preview: Cloudflare-like routing, headers, local-only script."""

import pathlib
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from llm_metrics import site_preview as sp
from llm_metrics import static_site as ss

REPO = pathlib.Path(__file__).resolve().parent.parent
STAGING = ss.SiteConfig("https://llmxchange.example.workers.dev")


def staging_files():
    return ss.render_site(
        STAGING, preview_at="2026-11-07T20:00:00Z", staging=True
    )


class RespondTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.files = staging_files()

    def test_routes_match_the_cloudflare_emulation(self):
        cases = {
            "/": (200, None),
            "/questions": (200, None),
            "/questions/": (307, "/questions"),
            "/questions/index.html": (307, "/questions"),
            "/how-to-measure-openai-ttft-latest": (
                301,
                "/how-to-measure-openai-ttft",
            ),
            "/nope": (404, None),
            "/_headers": (404, None),
            "/questions?x=1": (200, None),
        }
        for path, (status, location) in cases.items():
            got, headers, body = sp.respond(self.files, path)
            self.assertEqual(got, status, path)
            if location:
                self.assertIn(("Location", location), headers, path)
            elif status == 404:
                self.assertEqual(body, self.files["404.html"])

    def test_headers_and_types(self):
        _, headers, body = sp.respond(self.files, "/")
        names = dict(headers)
        self.assertEqual(names["X-Robots-Tag"], "noindex, nofollow")
        self.assertIn("default-src 'none'", names["Content-Security-Policy"])
        self.assertEqual(names["Content-Type"], "text/html; charset=utf-8")
        self.assertEqual(body, self.files["index.html"])
        _, headers, _ = sp.respond(self.files, "/assets/site.css")
        self.assertEqual(
            dict(headers)["Content-Type"], "text/css; charset=utf-8"
        )

    def test_drafts_absent_by_default(self):
        status, _, _ = sp.respond(self.files, "/openai-ttft")
        self.assertEqual(status, 404)


class ServerTest(unittest.TestCase):

    def test_serves_a_built_directory_on_localhost(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = pathlib.Path(tmp) / "site"
            ss.write_site(site, staging_files())
            files = sp.load_site(site)
            server = sp.http.server.ThreadingHTTPServer(
                ("127.0.0.1", 0), sp.handler_for(files)
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urllib.request.urlopen(base + "/questions") as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(
                    response.headers["X-Robots-Tag"], "noindex, nofollow"
                )
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(base + "/nope")
            self.assertEqual(error.exception.code, 404)

    def test_refuses_a_directory_that_is_not_a_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit):
                sp.load_site(pathlib.Path(tmp))


class ScriptTest(unittest.TestCase):

    def setUp(self):
        self.script = REPO / "scripts/site_preview.sh"
        if not self.script.exists():
            self.skipTest("scripts/site_preview.sh is not in the test image")

    def test_local_only_and_never_publishes(self):
        text = self.script.read_text()
        for forbidden in ("wrangler", "gcloud", "gsutil", "--publish-at"):
            self.assertNotIn(forbidden, text)
        self.assertIn("--staging", text)
        self.assertIn("--network none", text)
        self.assertIn('-p "127.0.0.1:$PORT:8000"', text)
        self.assertIn("http://localhost:$PORT", text)
        self.assertIn(".site-preview/", (REPO / ".gitignore").read_text())
        self.assertIn("site-preview", (REPO / "run.sh").read_text())


if __name__ == "__main__":
    unittest.main()
