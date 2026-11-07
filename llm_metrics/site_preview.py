"""Local preview server for a built static site, routed like Cloudflare.

Usage (normally via `./run.sh site-preview`, which builds the site first):
    python -m llm_metrics.site_preview --dir .site-preview/site
        [--host 127.0.0.1] [--port 8000]

Serves an already built `static_site` output directory read-only. Every
request is routed by `static_site.resolve`, the same offline emulation of
Cloudflare Workers Static Assets that the build's link checks use
(`drop-trailing-slash`, `404-page` and `_redirects`), and every response
carries the `_headers` rules. Files are read once at start-up: restart to
serve a rebuilt site. It never contacts any external service.

Known differences from Cloudflare (also in README): plain HTTP on
localhost, no edge caching or compression, `_headers` applied as a single
`/*` rule (the only form the generator writes), and Cloudflare's real
routing has not been verified beyond the staging checks.
"""

import argparse
import http.server
import mimetypes
import pathlib
import sys

from llm_metrics import static_site as ss

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".xml": "application/xml",
    ".txt": "text/plain; charset=utf-8",
}


def load_site(directory: pathlib.Path) -> dict[str, bytes]:
    """Reads a built site into {relative path: bytes}.

    Raises:
        SystemExit: If `directory` is not a static_site build.
    """
    directory = pathlib.Path(directory)
    if not (directory / ss.BUILD_MARKER).is_file():
        raise SystemExit(f"Not a static_site build: {directory}")
    return {
        str(path.relative_to(directory)): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def header_rules(files: dict[str, bytes]) -> list[tuple[str, str]]:
    """The `/*` rules from the generated `_headers` file."""
    rules, active = [], False
    for line in files.get("_headers", b"").decode().splitlines():
        if not line.startswith(" "):
            active = line.strip() == "/*"
        elif active and ":" in line:
            name, value = line.strip().split(":", 1)
            rules.append((name.strip(), value.strip()))
    return rules


def respond(files: dict[str, bytes], path: str):
    """(status, headers, body) for one GET request path."""
    path = path.split("?", 1)[0].split("#", 1)[0] or "/"
    status, target = ss.resolve(files, path)
    headers = header_rules(files)
    if status in (301, 302, 307, 308):
        return status, headers + [("Location", target)], b""
    body = files.get(target, b"Not found\n")
    suffix = pathlib.PurePosixPath(target).suffix
    kind = _TYPES.get(suffix) or (
        mimetypes.guess_type(target)[0] or "application/octet-stream"
    )
    return status, headers + [("Content-Type", kind)], body


def handler_for(files: dict[str, bytes]):
    class Handler(http.server.BaseHTTPRequestHandler):
        """Read-only GET/HEAD over the loaded site."""

        server_version = "llm-metrics-site-preview"

        def _send(self, include_body: bool):
            status, headers, body = respond(files, self.path)
            self.send_response(status)
            for name, value in headers:
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if include_body:
                self.wfile.write(body)

        def do_GET(self):  # pylint: disable=invalid-name
            self._send(True)

        def do_HEAD(self):  # pylint: disable=invalid-name
            self._send(False)

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m llm_metrics.site_preview", allow_abbrev=False
    )
    parser.add_argument("--dir", required=True, help="built site directory")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--url", help="address to print (e.g. when serving from Docker)"
    )
    options = parser.parse_args(argv)
    files = load_site(pathlib.Path(options.dir))
    server = http.server.ThreadingHTTPServer(
        (options.host, options.port), handler_for(files)
    )
    url = options.url or f"http://localhost:{options.port}"
    print(f"LLM Xchange preview: {url}  (Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
