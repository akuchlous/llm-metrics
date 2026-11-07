"""Deterministic static HTML site: question articles and metric pages.

Usage:
    python -m llm_metrics.static_site --output DIR --site-url https://HOST
        [--analytics SUMMARY.json --data-source real|synthetic]
        [--report REPORT.json]
        [--publish-at YYYY-MM-DDTHH:MM:SSZ | --preview-at YYYY-MM-DDTHH:MM:SSZ]

Questions and editions (Step 026):
- A question is a directory with `question.json`: a permanent opaque
  `question_id` (q0001), its stable path (e.g. /how-to-measure-openai-ttft),
  related metric pages, reviewed aliases and an ordered list of editions.
- Each edition (`editions/eN/`) is a Step 025 question `page.json` plus
  fragments, with `status` draft or approved. It carries no date: the
  publication time is assigned once, by `--publish-at`, and recorded in the
  archive manifest (`site_content/archive/manifest.json`, schema
  `llm-metrics.publication.v1`).
- Publishing freezes each approved, unarchived edition's HTML into
  `site_content/archive/reports/<UTC date>/<slug>[/rN]/index.html`. From
  then on those bytes are served verbatim; a changed archive file, changed
  edition content, unlisted archive file or other site URL stops the build.
- The stable question page shows the latest published edition with its
  edition history; `/` lists editions newest first; `/questions` groups them
  by question. Dated editions are canonical to the stable page. Educational
  questions need no dataset; an empty or synthetic metric page is noindex.
- `--preview-at` shows drafts at a provisional time, noindex, never archived.

Builds every page listed in `site_content/site.json` into `DIR` (clean URLs
as `<path>/index.html`), plus `assets/site.css` and, when a dataset is
given, a byte-exact copy of it under `data/analytics/<sha256>.json`. Needs no
HTTP service, database, GCP or provider access, and writes nothing else.

Owns: loading the reviewed page content, validating it, rendering pages with
Jinja2 (autoescaped, independent of Flask and SQL), page metadata (title,
description, canonical, Open Graph, breadcrumbs, JSON-LD), build-time checks
of the generated HTML, and a Yoast-inspired editorial report. It does not own
the analytics (`record_analytics` produces the only accepted input), hosting,
dated versions or redirects (later steps).

Separation of editorial text and data:
- Human-written text lives in `site_content/**/*.html` fragments and
  `page.json` metadata. Fragments are static HTML, not templates, so no
  number from a dataset can ever be written into the reviewed answer.
- Measured values are rendered only into the generated sections ("findings",
  "measurements", "provenance") from a validated `llm-metrics.analytics.v1`
  summary. Without one, those sections show an explicit "no validated
  measurements" state; no value is ever invented or defaulted.
- A question's answer has an explicit `answer_revision` and basis. A new
  dataset changes "data last refreshed", never the answer or its revision.

A dataset must be declared `real` or `synthetic`. Synthetic data (e.g. the
committed test fixtures) renders with a visible "synthetic test data" banner
and `noindex`, so a preview can never pass for published measurements.

Exit codes: 0 built, 1 invalid content or dataset or failed page checks
(nothing written), 2 bad arguments.
"""

import argparse
import dataclasses
import datetime
import difflib
import hashlib
import html.parser
import json
import math
import os
import pathlib
import re
import shutil
import sys
import tempfile
import urllib.parse

import jinja2
import markupsafe

from llm_metrics import cost_ledger
from llm_metrics import latency
from llm_metrics import outcomes
from llm_metrics import pricing
from llm_metrics import record_analytics
from llm_metrics import targets
from llm_metrics import workloads

PACKAGE_DIR = pathlib.Path(__file__).parent
CONTENT_DIR = PACKAGE_DIR / "site_content"
TEMPLATE_DIR = PACKAGE_DIR / "site_templates"
STYLESHEET_SOURCE = PACKAGE_DIR / "site_static" / "site.css"
STYLESHEET_PATH = "/assets/site.css"
BUILD_MARKER = ".llm-metrics-site"

# What a published TTFT number means. Bump when any of these change in a way
# that makes new numbers incomparable with old ones: the timer boundaries in
# `latency.measure_request`, success-only distributions with failures kept
# in reliability, nearest-rank percentiles, the record schema
# (`llm-metrics.attempt.v1`) or the summary schema (`llm-metrics.analytics.v1`).
# Workload and request-profile versions are tracked by their own ids.
METHODOLOGY_VERSION = "llm-metrics.ttft-methodology.v1"

# Static hosting may not allow response headers, so the policy is in a meta
# tag. Nothing executable is allowed (`default-src 'none'` also covers
# scripts); JSON-LD `application/ld+json` blocks are data that browsers never
# execute, so the policy does not hide them from crawlers.
CSP = (
    "default-src 'none'; style-src 'self'; img-src 'self'; base-uri 'none';"
    " form-action 'none'"
)

DATA_SOURCES = ("real", "synthetic")
MAX_SUMMARY_BYTES = 4 * 1024 * 1024
PAGE_KINDS = ("home", "hub", "directory", "question", "metric", "costs")
# Generated (never authored) measured-evidence view of a draft metric
# question, only in a provisional staging preview (Step 027b).
EVIDENCE_KIND = "evidence"
# Optional topic of a question (`question.json` "category").
CATEGORIES = ("Performance", "Cost", "Reliability", "Engineering")
# Questions listed per home page; later pages live at /page/N (N >= 2).
QUESTIONS_PER_PAGE = 50
# Breadcrumb parent of each loaded page kind; editions hang under their
# question's stable page.
_PARENTS = {
    "home": None,
    "hub": "/",
    "directory": "/",
    "question": "/questions",
    "metric": "/llm-performance",
    "costs": "/",
}
GENERATED_SECTIONS = {
    "question": ("findings", "setup"),
    "metric": ("measurements", "setup", "provenance", "methodology"),
    "costs": ("costs",),
}
# Order shown on the TTFT metric page: TTFT first, then the related latency
# and throughput metrics from the same requests.
METRIC_ORDER = (
    "ttft",
    "total_latency",
    "output_tokens_per_s",
    "output_chunks_per_s",
)

_PATH_RE = re.compile(
    r"^/(?:[a-z0-9]+(?:-[a-z0-9]+)*(?:/[a-z0-9]+(?:-[a-z0-9]+)*)*)?$"
)
_HOST_RE = re.compile(
    r"^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)
_DATE_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})$"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9./-]{0,100}$")

# Editorial fragments are reviewed repository content, but they are still
# checked against a small allowlist so a fragment cannot add scripts, styles,
# event handlers, images, forms or a second H1/H2 outline.
_FRAGMENT_TAGS = {
    "p",
    "ul",
    "ol",
    "li",
    "a",
    "code",
    "strong",
    "em",
    "h3",
    "br",
}
_VOID_TAGS = {"br", "meta", "link", "rect"}


class SiteError(Exception):
    """Content, dataset or generated pages are invalid. Nothing written."""


@dataclasses.dataclass(frozen=True)
class SiteConfig:
    """The validated public base URL, e.g. "https://llmxchange.com".

    Planned hostname only: building pages for it is not evidence that the
    host exists or serves them.
    """

    site_url: str

    def __post_init__(self):
        parts = urllib.parse.urlsplit(self.site_url)
        if (
            parts.scheme != "https"
            or not _HOST_RE.match(parts.netloc or "")
            or parts.path not in ("", "/")
            or parts.query
            or parts.fragment
        ):
            raise SiteError(
                "site URL must be https://<lowercase host> with no port,"
                " path, query or fragment."
            )

    @property
    def origin(self) -> str:
        return self.site_url.rstrip("/")

    def absolute(self, path: str) -> str:
        return self.origin + ("/" if path == "/" else path)


@dataclasses.dataclass(frozen=True)
class Section:
    id: str
    heading: str | None
    html: markupsafe.Markup | None
    generated: str | None


@dataclasses.dataclass(frozen=True)
class Page:
    """One page's reviewed content and metadata, from its `page.json`."""

    kind: str
    path: str
    title: str
    h1: str
    description: str
    breadcrumb_name: str
    sections: tuple[Section, ...]
    meta: dict
    parent: str | None = None
    # Where rel=canonical points; None means the page itself. Dated editions
    # point at their question's stable page (near-duplicate policy, D083).
    canonical_path: str | None = None
    robots: str | None = None
    extra: dict = dataclasses.field(default_factory=dict)

    @property
    def output_file(self) -> str:
        return (
            "index.html" if self.path == "/" else f"{self.path[1:]}/index.html"
        )

    @property
    def canonical(self) -> str:
        return self.canonical_path or self.path


@dataclasses.dataclass(frozen=True)
class Dataset:
    """A validated analytics summary and its identity."""

    summary: dict
    sha256: str
    data: bytes
    source: str  # "real" or "synthetic"
    # Allowlisted public projection (provisional staging previews only);
    # None publishes `data` itself, as before.
    public: bytes | None = None

    @property
    def public_bytes(self) -> bytes:
        return self.data if self.public is None else self.public

    @property
    def json_path(self) -> str:
        if self.public is None:
            return f"/data/analytics/{self.sha256}.json"
        digest = hashlib.sha256(self.public).hexdigest()
        return f"/data/analytics/{digest}.json"


# ---------------------------------------------------------------------------
# Content loading and validation


class _FragmentChecker(html.parser.HTMLParser):
    """Rejects any tag, attribute or link outside the fragment allowlist."""

    def __init__(self, source: str):
        super().__init__(convert_charrefs=True)
        self.source = source
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag not in _FRAGMENT_TAGS:
            raise SiteError(f"{self.source}: tag <{tag}> is not allowed.")
        for name, value in attrs:
            if not (tag == "a" and name == "href"):
                raise SiteError(
                    f"{self.source}: attribute {name!r} on <{tag}> is not"
                    " allowed."
                )
            if not (
                (value or "").startswith("https://")
                or _PATH_RE.match(value or "")
            ):
                raise SiteError(
                    f"{self.source}: link must be an internal path or https."
                )
            self.links.append(value)

    def handle_comment(self, data):
        raise SiteError(f"{self.source}: comments are not allowed.")

    def handle_decl(self, decl):
        raise SiteError(f"{self.source}: declarations are not allowed.")

    def handle_pi(self, data):
        raise SiteError(
            f"{self.source}: processing instructions are not allowed."
        )


def check_fragment(text: str, source: str) -> list[str]:
    """Validates an editorial fragment; returns its link targets."""
    checker = _FragmentChecker(source)
    checker.feed(text)
    checker.close()
    return checker.links


def _string(meta: dict, key: str, source: str, *, limit: int = 300) -> str:
    value = meta.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise SiteError(f"{source}: {key} must be a non-empty string.")
    return value


def _load_page(directory: pathlib.Path, content_dir: pathlib.Path) -> Page:
    source = f"site_content/{directory.relative_to(content_dir)}/page.json"
    try:
        meta = json.loads((directory / "page.json").read_text("utf-8"))
    except (OSError, ValueError):
        raise SiteError(f"{source}: missing or not JSON.") from None
    kind = meta.get("kind")
    if kind not in PAGE_KINDS:
        raise SiteError(f"{source}: unknown kind.")
    path = _string(meta, "path", source)
    if not _PATH_RE.match(path) or (path == "/") != (kind == "home"):
        raise SiteError(f"{source}: invalid path.")
    sections = []
    for entry in meta.get("sections") or []:
        section_id = entry.get("id")
        if not isinstance(section_id, str) or not re.match(
            r"^[a-z]+$", section_id
        ):
            raise SiteError(f"{source}: invalid section id.")
        heading = entry.get("heading")
        if heading is not None and not isinstance(heading, str):
            raise SiteError(f"{source}: invalid section heading.")
        if "generated" in entry:
            if entry["generated"] not in GENERATED_SECTIONS.get(kind, ()):
                raise SiteError(f"{source}: unknown generated section.")
            sections.append(
                Section(section_id, heading, None, entry["generated"])
            )
            continue
        fragment_path = directory / str(entry.get("file"))
        if fragment_path.parent != directory or not fragment_path.is_file():
            raise SiteError(f"{source}: missing fragment for {section_id}.")
        text = fragment_path.read_text("utf-8")
        check_fragment(
            text, f"site_content/{fragment_path.relative_to(content_dir)}"
        )
        # Reviewed repository content, checked against the allowlist above.
        sections.append(
            Section(section_id, heading, markupsafe.Markup(text), None)
        )
    if not sections:
        raise SiteError(f"{source}: no sections.")
    if len({s.id for s in sections}) != len(sections):
        raise SiteError(f"{source}: duplicate section ids.")
    if kind == "question":
        _check_question_meta(meta, source)
    return Page(
        kind=kind,
        path=path,
        title=_string(meta, "title", source, limit=110),
        h1=_string(meta, "h1", source, limit=150),
        description=_string(meta, "meta_description", source),
        breadcrumb_name=_string(meta, "breadcrumb_name", source, limit=80),
        sections=tuple(sections),
        meta=meta,
        parent=_PARENTS[kind],
    )


def _check_question_meta(meta: dict, source: str) -> None:
    for key in ("answer_revision", "editorial_revision"):
        if not _SAFE_ID_RE.match(_string(meta, key, source)):
            raise SiteError(f"{source}: {key} has unsafe characters.")
    basis = meta.get("answer_basis")
    reviewed = meta.get("answer_reviewed_dataset_sha256")
    if basis == "methodology":
        if reviewed is not None:
            raise SiteError(f"{source}: methodology answers cite no dataset.")
    elif basis == "dataset":
        if not isinstance(reviewed, str) or not _SHA256_RE.match(reviewed):
            raise SiteError(
                f"{source}: a dataset-based answer must name the reviewed"
                " dataset's SHA-256."
            )
    else:
        raise SiteError(
            f"{source}: answer_basis must be methodology or dataset."
        )
    for key in ("date_published", "date_modified"):
        value = meta.get(key)
        if value is not None and (
            not isinstance(value, str) or not _DATE_RE.match(value)
        ):
            raise SiteError(
                f"{source}: {key} must be ISO 8601 with a UTC offset."
            )
    if meta.get("date_modified") and not meta.get("date_published"):
        raise SiteError(f"{source}: date_modified needs date_published.")
    authors = meta.get("authors")
    if not isinstance(authors, list):
        raise SiteError(f"{source}: authors must be a list (may be empty).")
    for author in authors:
        if (
            not isinstance(author, dict)
            or set(author) - {"name", "url"}
            or not isinstance(author.get("name"), str)
            or not author["name"].strip()
            or not str(author.get("url", "https://")).startswith("https://")
        ):
            raise SiteError(f"{source}: invalid author.")
    related = meta.get("related_metric")
    if related is not None and not _PATH_RE.match(str(related)):
        raise SiteError(f"{source}: related_metric must be a page path.")
    if basis == "dataset":
        # Dated editions are immutable, so a data-backed answer needs an
        # immutable metrics snapshot to cite; that is not implemented yet.
        raise SiteError(
            f"{source}: dataset-based answers need metric snapshots, which"
            " are not supported yet."
        )


def load_pages(
    content_dir: pathlib.Path = CONTENT_DIR,
) -> tuple[dict, list[Page], list["Question"]]:
    """Loads `site.json`: plain pages and registered questions, in order.

    A listed directory holding `question.json` is a question (see
    `load_question`); any other holds one `page.json`.
    """
    try:
        site = json.loads((content_dir / "site.json").read_text("utf-8"))
    except (OSError, ValueError):
        raise SiteError(
            "site_content/site.json is missing or not JSON."
        ) from None
    pages, questions = [], []
    for entry in site.get("pages", []):
        directory = content_dir / entry
        if (directory / "question.json").is_file():
            questions.append(load_question(directory, content_dir))
        else:
            pages.append(_load_page(directory, content_dir))
    paths = [page.path for page in pages] + [q.path for q in questions]
    paths += [alias for q in questions for alias in q.aliases]
    if len(set(paths)) != len(paths):
        raise SiteError("Two pages, questions or aliases share a path.")
    for field in ("title", "description", "h1"):
        values = [getattr(page, field) for page in pages]
        if len(set(values)) != len(values):
            raise SiteError(f"Page {field}s must be unique.")
    kinds = [p.kind for p in pages]
    if (
        kinds.count("home") != 1
        or "/llm-performance" not in paths
        or [p.path for p in pages if p.kind == "directory"] != ["/questions"]
    ):
        raise SiteError(
            "The site needs one home page, the /llm-performance hub and the"
            " /questions directory."
        )
    _check_registry(questions)
    return site, pages, questions


# ---------------------------------------------------------------------------
# Question registry and immutable editions

_QUESTION_ID_RE = re.compile(r"^q[0-9]{4}$")
_EDITION_ID_RE = re.compile(r"^e[0-9]+$")
_PUBLISHED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$")
EDITION_STATUSES = ("draft", "approved")
PUBLICATION_SCHEMA = "llm-metrics.publication.v1"
MANIFEST_NAME = "manifest.json"
# Above this title similarity two questions must be explicitly reviewed as
# distinct intents (TTFT vs total latency, other workload or region...).
_SIMILAR_TITLE_RATIO = 0.85
# Numbers with measurement units in an answer that cites no dataset would
# be unverified empirical claims; such editions are refused.
_EMPIRICAL_RE = re.compile(
    r"\b\d[\d,.]*\s?(?:ms|milliseconds|tokens/s|%)", re.IGNORECASE
)


@dataclasses.dataclass(frozen=True)
class Edition:
    """One reviewed answer edition of a question (`editions/<id>/`).

    Its content is a Step 025 question `page.json` plus fragments. The
    publication time is not in the content: it is assigned once, when the
    edition is frozen into the archive, and recorded in the manifest.
    """

    edition_id: str
    status: str
    summary: str
    what_changed: str | None
    source_commit: str | None
    page: Page
    content_sha256: str


@dataclasses.dataclass(frozen=True)
class Question:
    """A permanent question identity from `question.json`."""

    question_id: str
    path: str
    breadcrumb_name: str
    related_metrics: tuple[str, ...]
    aliases: tuple[str, ...]
    reviewed_distinct_from: tuple[str, ...]
    editions: tuple[Edition, ...]
    category: str | None = None


def _content_sha256(directory: pathlib.Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(directory.iterdir()):
        if path.is_file():
            digest.update(
                path.name.encode() + b"\0" + path.read_bytes() + b"\0"
            )
    return digest.hexdigest()


def load_question(
    directory: pathlib.Path, content_dir: pathlib.Path
) -> Question:
    """Loads one registry entry and its editions, validating identity rules."""
    source = f"site_content/{directory.relative_to(content_dir)}/question.json"
    try:
        meta = json.loads((directory / "question.json").read_text("utf-8"))
    except (OSError, ValueError):
        raise SiteError(f"{source}: missing or not JSON.") from None
    question_id = meta.get("question_id")
    if not isinstance(question_id, str) or not _QUESTION_ID_RE.match(
        question_id
    ):
        raise SiteError(f"{source}: question_id must look like q0001.")
    path = _string(meta, "path", source)
    if not _PATH_RE.match(path) or path == "/" or path.startswith("/reports"):
        raise SiteError(f"{source}: invalid question path.")
    lists = {}
    for key in ("related_metrics", "aliases", "reviewed_distinct_from"):
        value = meta.get(key, [])
        if not isinstance(value, list) or not all(
            isinstance(v, str) for v in value
        ):
            raise SiteError(f"{source}: {key} must be a list of strings.")
        lists[key] = tuple(value)
    category = meta.get("category")
    if category is not None and category not in CATEGORIES:
        raise SiteError(f"{source}: category must be one of {CATEGORIES}.")
    for alias in lists["aliases"]:
        if not _PATH_RE.match(alias) or alias == path:
            raise SiteError(f"{source}: invalid alias.")
    editions = []
    for edition_id in meta.get("editions") or []:
        if not isinstance(edition_id, str) or not _EDITION_ID_RE.match(
            edition_id
        ):
            raise SiteError(f"{source}: invalid edition id.")
        edition_dir = directory / "editions" / edition_id
        page = _load_page(edition_dir, content_dir)
        esource = (
            f"site_content/{edition_dir.relative_to(content_dir)}/page.json"
        )
        if page.kind != "question" or page.path != path:
            raise SiteError(f"{esource}: must be a question page at {path}.")
        info = page.meta
        if info.get("status") not in EDITION_STATUSES:
            raise SiteError(f"{esource}: status must be draft or approved.")
        for key in ("date_published", "date_modified", "published_at"):
            if key in info:
                raise SiteError(
                    f"{esource}: {key} is assigned at publication, not in"
                    " content."
                )
        what_changed = info.get("what_changed")
        if (what_changed is None) != (not editions):
            raise SiteError(
                f"{esource}: what_changed is required for every edition"
                " after the first, and only then."
            )
        commit = info.get("source_commit")
        if commit is not None and not _COMMIT_RE.match(str(commit)):
            raise SiteError(f"{esource}: invalid source_commit.")
        if (
            editions
            and info["answer_revision"]
            == editions[-1].page.meta["answer_revision"]
        ):
            raise SiteError(
                f"{esource}: a new edition needs a new answer_revision."
            )
        if info["answer_basis"] == "methodology":
            for section in page.sections:
                if section.html is not None and _EMPIRICAL_RE.search(
                    section.html.striptags()
                ):
                    raise SiteError(
                        f"{esource}: section {section.id} states a measured"
                        " value but the answer cites no dataset."
                    )
        editions.append(
            Edition(
                edition_id=edition_id,
                status=info["status"],
                summary=_string(info, "summary", esource),
                what_changed=what_changed,
                source_commit=commit,
                page=page,
                content_sha256=_content_sha256(edition_dir),
            )
        )
    if not editions:
        raise SiteError(f"{source}: a question needs at least one edition.")
    return Question(
        question_id=question_id,
        path=path,
        breadcrumb_name=_string(meta, "breadcrumb_name", source, limit=80),
        editions=tuple(editions),
        category=category,
        **lists,
    )


def _check_registry(questions: list[Question]) -> None:
    ids = [q.question_id for q in questions]
    if len(set(ids)) != len(ids):
        raise SiteError("Duplicate question_id in the registry.")
    known = set(ids)
    for question in questions:
        if set(question.reviewed_distinct_from) - known:
            raise SiteError(
                f"{question.question_id}: reviewed_distinct_from names an"
                " unknown question."
            )
    for i, first in enumerate(questions):
        for second in questions[i + 1 :]:
            ratio = difflib.SequenceMatcher(
                None,
                first.editions[-1].page.h1.lower(),
                second.editions[-1].page.h1.lower(),
            ).ratio()
            reviewed = (
                second.question_id in first.reviewed_distinct_from
                or first.question_id in second.reviewed_distinct_from
            )
            if ratio >= _SIMILAR_TITLE_RATIO and not reviewed:
                raise SiteError(
                    f"{first.question_id} and {second.question_id} look like"
                    " the same question; merge them or record an explicit"
                    " reviewed_distinct_from."
                )


@dataclasses.dataclass(frozen=True)
class Published:
    """An edition with its publication time and dated route."""

    question: Question
    edition: Edition
    published_at: str
    route: str
    frozen: bytes | None  # archived HTML, served verbatim when present


def edition_route(
    question_path: str, published_at: str, same_day_index: int
) -> str:
    """`/reports/<UTC date>/<slug>`, then `/r2`, `/r3` for the same date."""
    route = f"/reports/{published_at[:10]}{question_path}"
    return route if same_day_index == 1 else f"{route}/r{same_day_index}"


def _canonical_json(value) -> bytes:
    return (
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def load_manifest(archive_dir: pathlib.Path) -> dict:
    """Reads the publication manifest; an absent archive is an empty one."""
    path = archive_dir / MANIFEST_NAME
    if not path.exists():
        return {"schema_version": PUBLICATION_SCHEMA, "editions": []}
    try:
        manifest = json.loads(path.read_text("utf-8"))
    except ValueError:
        raise SiteError("Archive manifest is not JSON.") from None
    if (
        manifest.get("schema_version") != PUBLICATION_SCHEMA
        or not isinstance(manifest.get("editions"), list)
        or path.read_bytes() != _canonical_json(manifest)
    ):
        raise SiteError("Archive manifest is malformed or not canonical.")
    return manifest


def plan_editions(
    questions: list[Question],
    config: SiteConfig,
    archive_dir: pathlib.Path,
    *,
    freeze_at: str | None = None,
    preview_at: str | None = None,
    staging: bool = False,
) -> tuple[list[Published], list[dict]]:
    """Decides which editions are published and where.

    - Archived editions (in the manifest) are published at their recorded
      time and served from their archived bytes, which must still match the
      recorded SHA-256, as must the edition's source content.
    - With `freeze_at`, approved editions not yet archived are published at
      that time (new manifest entries are returned for the caller to write).
    - With `preview_at`, every unarchived edition, drafts included, is shown
      at that time for review only (never written to the archive).
    - With `staging` (a preview for a temporary public host), only approved
      editions are shown, and only on their stable question page: no dated
      `/reports/...` edition is generated, so no artificial history exists.

    Returns:
        (published editions, new manifest entries).

    Raises:
        SiteError: Orphaned or modified archive content, out-of-order or
            unapproved publication, or a site URL other than the archive's.
    """
    manifest = load_manifest(archive_dir)
    entries = manifest["editions"]
    by_key = {
        (q.question_id, e.edition_id): (q, e)
        for q in questions
        for e in q.editions
    }
    seen = set()
    published, new_entries = [], []
    for entry in entries:
        key = (entry.get("question_id"), entry.get("edition_id"))
        if key not in by_key or key in seen:
            raise SiteError(
                f"Archive entry {entry.get('route')} has no edition."
            )
        seen.add(key)
        question, edition = by_key[key]
        if entry.get("site_url") != config.origin:
            raise SiteError(
                "Archived editions were published for"
                f" {entry.get('site_url')}; build with that --site-url."
            )
        if edition.status != "approved" or edition.content_sha256 != entry.get(
            "content_sha256"
        ):
            raise SiteError(
                f"Edition {key} changed after publication; add a new edition"
                " instead."
            )
        path = archive_dir / entry["route"][1:] / "index.html"
        if path.is_symlink() or not path.is_file():
            raise SiteError(f"Archived page missing: {entry['route']}")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != entry.get("html_sha256"):
            raise SiteError(f"Archived page was modified: {entry['route']}")
        published.append(
            Published(
                question, edition, entry["published_at"], entry["route"], data
            )
        )
    archived_files = (
        {
            str(p.relative_to(archive_dir))
            for p in archive_dir.rglob("*")
            if p.is_file()
        }
        if archive_dir.exists()
        else set()
    )
    expected_files = {MANIFEST_NAME} | {
        f"{e['route'][1:]}/index.html" for e in entries
    }
    stray = archived_files - expected_files
    moment = freeze_at or preview_at
    pending = [
        (q, e)
        for q in questions
        for e in q.editions
        if (q.question_id, e.edition_id) not in seen
        and (
            (preview_at is not None and not staging)
            or ((freeze_at is not None or staging) and e.status == "approved")
        )
    ]
    for question, edition in pending:
        earlier = [p for p in published if p.question is question]
        if earlier and moment <= max(p.published_at for p in earlier):
            raise SiteError(
                "A new edition must be published after the previous one."
            )
        later = question.editions.index(edition)
        if any(question.editions.index(p.edition) > later for p in earlier):
            raise SiteError("Editions must be published in registry order.")
        same_day = sum(p.published_at[:10] == moment[:10] for p in earlier) + 1
        route = (
            question.path
            if staging
            else edition_route(question.path, moment, same_day)
        )
        published.append(Published(question, edition, moment, route, None))
        if freeze_at is not None:
            new_entries.append(
                {
                    "question_id": question.question_id,
                    "edition_id": edition.edition_id,
                    "route": route,
                    "published_at": moment,
                    "answer_revision": edition.page.meta["answer_revision"],
                    "editorial_revision": edition.page.meta[
                        "editorial_revision"
                    ],
                    "answer_basis": edition.page.meta["answer_basis"],
                    "dataset_sha256": None,
                    "methodology_version": METHODOLOGY_VERSION,
                    "content_sha256": edition.content_sha256,
                    "source_commit": edition.source_commit,
                    "site_url": config.origin,
                }
            )
    if stray:
        # A freeze interrupted after writing pages but before the manifest
        # leaves pages without entries; re-running the same freeze adopts
        # them only if they are byte-identical (checked by the caller).
        new_routes = {f"{e['route'][1:]}/index.html" for e in new_entries}
        if stray - new_routes:
            raise SiteError(
                f"Archive has unlisted files: {sorted(stray - new_routes)}"
            )
    return published, new_entries


# ---------------------------------------------------------------------------
# Dataset loading and validation


def _reject_duplicates(pairs):
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise SiteError("Dataset JSON has duplicate keys.")
    return dict(pairs)


def _reject_constant(unused_name):
    raise SiteError("Dataset JSON has a non-finite number.")


def _number_or_none(value, label):
    if value is None:
        return
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise SiteError(
            f"Dataset {label} must be a non-negative number or null."
        )


def _count(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SiteError(f"Dataset {label} must be a non-negative integer.")
    return value


def validate_summary(summary, expected_population: dict) -> None:
    """Checks the parts of an `llm-metrics.analytics.v1` summary pages use.

    Raises:
        SiteError: Describing the first problem (field names only).
    """
    if not isinstance(summary, dict):
        raise SiteError("Dataset must be a JSON object.")
    if summary.get("schema_version") != record_analytics.SCHEMA_VERSION:
        raise SiteError("Dataset is not an llm-metrics.analytics.v1 summary.")
    population = summary.get("population")
    if not isinstance(population, dict):
        raise SiteError("Dataset population is missing.")
    scope = {
        k: v
        for k, v in population.items()
        if k not in ("start_inclusive", "end_exclusive")
    }
    if scope != expected_population:
        raise SiteError("Dataset population does not match this page.")
    for key in ("start_inclusive", "end_exclusive"):
        try:
            datetime.datetime.strptime(
                population.get(key, ""), "%Y-%m-%dT%H:%M:%SZ"
            )
        except (TypeError, ValueError):
            raise SiteError(
                f"Dataset population.{key} is not UTC time."
            ) from None
    reliability = summary.get("reliability")
    if not isinstance(reliability, dict):
        raise SiteError("Dataset reliability is missing.")
    attempts = _count(reliability.get("attempts"), "reliability.attempts")
    successes = _count(reliability.get("successes"), "reliability.successes")
    failures = _count(reliability.get("failures"), "reliability.failures")
    if attempts == 0 or successes + failures != attempts:
        raise SiteError("Dataset reliability counts are inconsistent.")
    by_category = reliability.get("failures_by_category")
    if (
        not isinstance(by_category, dict)
        or set(by_category) != set(outcomes.FAILURE_CATEGORIES)
        or sum(_count(v, "failures_by_category") for v in by_category.values())
        != failures
    ):
        raise SiteError("Dataset failure categories are inconsistent.")
    metrics = summary.get("metrics")
    if not isinstance(metrics, dict) or set(metrics) != set(latency.METRICS):
        raise SiteError("Dataset metrics are missing or unexpected.")
    for name, metric in metrics.items():
        if (
            not isinstance(metric, dict)
            or metric.get("unit") != latency.METRICS[name][1]
        ):
            raise SiteError(f"Dataset metric {name} has a wrong unit.")
        count = _count(metric.get("count"), f"{name}.count")
        for key in ("p50", "p95", "min", "max"):
            _number_or_none(metric.get(key), f"{name}.{key}")
            if (metric.get(key) is None) != (count == 0):
                raise SiteError(
                    f"Dataset {name}.{key} disagrees with its count."
                )
        if count > successes:
            raise SiteError(f"Dataset {name} has more values than successes.")
    if metrics["ttft"]["count"] != successes:
        raise SiteError("Every successful attempt must have a TTFT value.")
    window = summary.get("data_window")
    if not isinstance(window, dict):
        raise SiteError("Dataset data_window is missing.")
    for key in ("earliest_recorded_at", "latest_recorded_at"):
        try:
            record_analytics.parse_record_time(window.get(key, ""))
        except (TypeError, ValueError):
            raise SiteError(
                f"Dataset data_window.{key} is not UTC time."
            ) from None
    cost, tokens = summary.get("cost_usd"), summary.get("tokens")
    if not isinstance(cost, dict) or not isinstance(tokens, dict):
        raise SiteError("Dataset cost or tokens are missing.")
    _number_or_none(cost.get("known_total_cost"), "known_total_cost")
    _count(
        cost.get("failed_attempts_cost_unknown"), "failed_attempts_cost_unknown"
    )
    for key in ("input_tokens", "output_tokens", "cached_input_tokens_known"):
        _number_or_none(tokens.get(key), key)
    _count(
        tokens.get("cached_input_tokens_unknown_count"), "cached unknown count"
    )
    evidence = summary.get("evidence")
    if (
        not isinstance(evidence, dict)
        or evidence.get("record_count") != attempts
        or not _SHA256_RE.match(str(evidence.get("manifest_sha256")))
    ):
        raise SiteError("Dataset evidence is missing or inconsistent.")
    caveats = summary.get("caveats")
    if not isinstance(caveats, list) or not all(
        isinstance(c, dict)
        and isinstance(c.get("code"), str)
        and isinstance(c.get("detail"), str)
        for c in caveats
    ):
        raise SiteError("Dataset caveats are malformed.")
    slots = summary.get("slot_completeness")
    if slots is not None and (
        not isinstance(slots, dict) or not isinstance(slots.get("states"), dict)
    ):
        raise SiteError("Dataset slot_completeness is malformed.")


def load_dataset(
    path: pathlib.Path, source: str, expected_population: dict
) -> Dataset:
    """Reads, canonicality-checks and validates an analytics summary file."""
    if source not in DATA_SOURCES:
        raise SiteError("--data-source must be real or synthetic.")
    path = pathlib.Path(path)
    if path.is_symlink() or not path.is_file():
        raise SiteError(f"Dataset is not a regular file: {path}")
    if path.stat().st_size > MAX_SUMMARY_BYTES:
        raise SiteError("Dataset file is too large.")
    data = path.read_bytes()
    if not data.strip():
        raise SiteError("Dataset file is empty.")
    try:
        summary = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_reject_duplicates,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SiteError("Dataset is not UTF-8 JSON.") from None
    try:
        canonical = record_analytics.encode_summary(summary)
    except record_analytics.AnalyticsInputError:
        raise SiteError("Dataset has a non-finite number.") from None
    if canonical != data:
        # Only the exact bytes `record_analytics` wrote are accepted, so the
        # published fingerprint identifies exactly what was validated.
        raise SiteError("Dataset is not in canonical form (edited by hand?).")
    validate_summary(summary, expected_population)
    return Dataset(summary, hashlib.sha256(data).hexdigest(), data, source)


# ---------------------------------------------------------------------------
# View preparation (formatting only; no new facts)


def _utc_text(text: str) -> str:
    """'2026-01-05T19:45:09.495250Z' -> '2026-01-05 19:45:09 UTC'."""
    return text[:19].replace("T", " ") + " UTC"


def _format_metric(metric: str, value) -> str | None:
    if value is None:
        return None
    unit = latency.METRICS[metric][1]
    return f"{value:,.0f} ms" if unit == "ms" else f"{value:,.1f} {unit}"


def _format_count(value) -> str | None:
    return None if value is None else f"{value:,}"


# Step 027b pilot gates for a provisional (partial-window) staging preview.
# They are deliberately separate from the production path (publish_runner's
# metrics lane, which never passes `provisional`).
PROVISIONAL_MIN_SUCCESSES = 30
PROVISIONAL_MAX_UNRECORDED_SHARE = 0.05
# Fields of the private summary that may be published (allowlist).
_PUBLIC_DROP = ("evidence.records", "slot_completeness.problems")


def _public_projection(summary: dict) -> dict:
    """The summary without per-record ids or object names (canonical)."""
    public = json.loads(json.dumps(summary))
    public["evidence"].pop("records", None)
    if public.get("slot_completeness"):
        public["slot_completeness"].pop("problems", None)
    for metric in public["metrics"].values():
        metric.pop("latest", None)
    public["public_projection"] = {
        "of_dataset_sha256": None,  # filled by the caller
        "removed": list(_PUBLIC_DROP) + ["metrics.*.latest"],
    }
    return public


def _provisional_gate(
    dataset: Dataset, provisional: bool, staging: bool
) -> Dataset:
    """Applies the provisional staging-preview gates, when requested.

    Returns the dataset unchanged without `provisional`; otherwise with an
    allowlisted public projection and a provisional label.

    Raises:
        SiteError: A provisional preview outside staging, without real data,
            or failing the pilot gates.
    """
    summary = dataset.summary
    codes = {c["code"] for c in summary["caveats"]}
    if not provisional:
        # Production partial-day data stays governed by publish_runner's
        # metrics lane (refused unless --allow-preliminary); this preview
        # path is never used there.
        return dataset
    if not staging or dataset.source != "real":
        raise SiteError(
            "--provisional-metrics needs --staging and a real dataset."
        )
    slots = summary.get("slot_completeness")
    if not slots or not slots.get("expected_slots"):
        raise SiteError("A provisional preview needs collector slot evidence.")
    states = slots["states"]
    unrecorded = states.get("missing", 0) + states.get(
        "claim_without_record", 0
    )
    successes = summary["reliability"]["successes"]
    if successes < PROVISIONAL_MIN_SUCCESSES:
        raise SiteError(
            f"Only {successes} successes; a provisional preview needs"
            f" {PROVISIONAL_MIN_SUCCESSES}."
        )
    if unrecorded > PROVISIONAL_MAX_UNRECORDED_SHARE * slots["expected_slots"]:
        raise SiteError("Too many due slots have no record for a preview.")
    cutoff = _utc_text(summary["population"]["end_exclusive"])
    complete = (
        "partial_day" not in codes
        and slots["expected_slots"] == slots["policy"]["max_slots"]
        and unrecorded == 0
    )
    label = (
        f"Verified complete pilot, through {cutoff}; staging preview, not a"
        " provider-wide benchmark."
        if complete
        else f"Partial pilot, as of {cutoff}; not a 24-hour result or"
        " provider-wide benchmark."
    )
    public = _public_projection(summary)
    public["public_projection"]["of_dataset_sha256"] = dataset.sha256
    public_bytes = record_analytics.encode_summary(public)
    return dataclasses.replace(
        dataset,
        summary={
            **summary,
            "_provisional": {
                "label": label,
                "due_slots": slots["expected_slots"],
                "policy_slots": slots["policy"]["max_slots"],
                "complete": complete,
            },
        },
        public=public_bytes,
    )


def data_view(dataset: Dataset) -> dict:
    """Template values from a validated summary. Display rounding only."""
    summary = dataset.summary
    population = summary["population"]
    reliability = summary["reliability"]
    metrics = summary["metrics"]
    ttft = metrics["ttft"]
    codes = {caveat["code"] for caveat in summary["caveats"]}
    preliminary = []
    if "small_sample" in codes:
        preliminary.append(
            f"based on {ttft['count']:,} successful requests; percentiles from"
            " small samples are unstable."
        )
    if "p95_is_sample_max" in codes:
        preliminary.append("with under 20 successes, p95 equals the maximum.")
    if "partial_day" in codes:
        preliminary.append("the data window is shorter than 24 hours.")
    rows = []
    for name in METRIC_ORDER:
        metric = metrics[name]
        rows.append(
            {
                "label": f"{latency.METRICS[name][0]} ({metric['unit']})",
                "count": f"{metric['count']:,}",
                **{
                    k: _format_metric(name, metric[k])
                    for k in ("p50", "p95", "min", "max")
                },
            }
        )
    chart = None
    if ttft["count"]:
        scale, label_width = 300, 130
        bars = []
        for i, (label, key) in enumerate(
            (
                ("Min", "min"),
                ("Median (p50)", "p50"),
                ("p95", "p95"),
                ("Max", "max"),
            )
        ):
            width = (
                round(ttft[key] / ttft["max"] * scale, 1) if ttft["max"] else 0
            )
            bars.append(
                {
                    "label": label,
                    "y": 10 + i * 32,
                    "width": width,
                    "text": _format_metric("ttft", ttft[key]),
                }
            )
        chart = {
            "title": f"TTFT of {ttft['count']:,} successful requests",
            "width": label_width + scale + 90,
            "height": 10 + 4 * 32,
            "label_width": label_width,
            "bars": bars,
        }
    slots = summary["slot_completeness"]
    return {
        "source": dataset.source,
        "schema_version": summary["schema_version"],
        "record_schema_version": summary["record_schema_version"],
        "dataset_sha256": dataset.sha256,
        "manifest_sha256": summary["evidence"]["manifest_sha256"],
        "record_count": f"{summary['evidence']['record_count']:,}",
        "json_path": dataset.json_path,
        "public_sha256": None
        if dataset.public is None
        else hashlib.sha256(dataset.public).hexdigest(),
        "population": {
            **population,
            "origin": (
                f"{population['origin_cloud']} {population['origin_region']}"
            ),
        },
        "window": {
            "start": _utc_text(population["start_inclusive"]),
            "end": _utc_text(population["end_exclusive"]),
            "start_iso": population["start_inclusive"],
            "end_iso": population["end_exclusive"],
            "latest": _utc_text(summary["data_window"]["latest_recorded_at"]),
            "latest_iso": summary["data_window"]["latest_recorded_at"],
        },
        "ttft": {
            "count": f"{ttft['count']:,}",
            "p50": _format_metric("ttft", ttft["p50"]),
            "p95": _format_metric("ttft", ttft["p95"]),
        },
        "metric_rows": rows,
        "provisional": summary.get("_provisional"),
        "chart": chart,
        "preliminary": " ".join(p[0].upper() + p[1:] for p in preliminary),
        "reliability": {
            "attempts": f"{reliability['attempts']:,}",
            "successes": f"{reliability['successes']:,}",
            "failures": f"{reliability['failures']:,}",
            "success_rate": (
                f"{reliability['successes'] / reliability['attempts']:.1%}"
                f" ({reliability['successes']:,} of"
                f" {reliability['attempts']:,})"
            ),
            "by_category": [
                {
                    "label": label,
                    "count": f"{reliability['failures_by_category'][code]:,}",
                }
                for code, label in outcomes.FAILURE_CATEGORIES.items()
                if reliability["failures_by_category"][code]
            ],
        },
        "slots": None
        if slots is None
        else {
            "expected": slots.get("expected_slots"),
            **{
                k: slots["states"].get(k, 0)
                for k in (
                    "recorded_success",
                    "recorded_failure",
                    "claim_without_record",
                    "missing",
                )
            },
        },
        "cost": {
            "known_total_cost": None
            if summary["cost_usd"]["known_total_cost"] is None
            else f"${summary['cost_usd']['known_total_cost']:.6f}",
            "unknown_count": summary["cost_usd"][
                "failed_attempts_cost_unknown"
            ],
        },
        "tokens": {
            "input_tokens": _format_count(summary["tokens"]["input_tokens"]),
            "output_tokens": _format_count(summary["tokens"]["output_tokens"]),
            "cached_known": _format_count(
                summary["tokens"]["cached_input_tokens_known"]
            ),
            "cached_unknown": summary["tokens"][
                "cached_input_tokens_unknown_count"
            ],
        },
        "caveats": summary["caveats"],
    }


def setup_rows() -> list[dict]:
    """The measurement setup, read from the code that defines it."""
    profile = targets.OPENAI
    workload = workloads.get_workload("interactive-chat-v1")
    price = pricing.PRICES[(profile.provider, profile.model)]
    settings = ", ".join(f"{key}={value}" for key, value in profile.settings)
    return [
        {
            "label": "Provider and model",
            "value": f"{profile.provider} {profile.model}",
        },
        {"label": "Request profile", "value": profile.profile_id},
        {"label": "Endpoint", "value": profile.endpoint},
        {"label": "Request settings", "value": settings},
        {"label": "Reasoning", "value": profile.reasoning},
        {"label": "Cache policy", "value": profile.cache_policy},
        {
            "label": "Workload",
            "value": f"{workload.workload_id} ({workload.name})",
        },
        {
            "label": "Requested output cap",
            "value": f"{workload.max_output_tokens} tokens",
        },
        {
            "label": "Designed input size",
            "value": (
                f"about {workload.target_input_tokens:,} tokens (a design"
                " target, not a provider count)"
            ),
        },
        {
            "label": "Prompt SHA-256",
            "value": hashlib.sha256(workload.prompt.encode()).hexdigest(),
        },
        {
            "label": "Timer",
            "value": (
                "time.perf_counter() from just before the streaming request"
                " to the first response.output_text.delta event"
            ),
        },
        {
            "label": "Percentiles",
            "value": "nearest rank, successful requests only",
        },
        {
            "label": "List prices used for cost (USD per 1M tokens)",
            "value": (
                f"input {price.input_per_1m}, cached input"
                f" {price.cached_input_per_1m}, output {price.output_per_1m}"
            ),
        },
        {"label": "Methodology version", "value": METHODOLOGY_VERSION},
    ]


# ---------------------------------------------------------------------------
# Structured data


def json_ld(value: dict) -> markupsafe.Markup:
    """Serializes JSON-LD that cannot close its `<script>` element.

    `<`, `>` and `&` are escaped as JSON unicode escapes, which JSON parsers
    read back unchanged, so no value can produce `</script>` or `<!--`.
    """
    text = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    for raw, escaped in (
        ("<", "\\u003c"),
        (">", "\\u003e"),
        ("&", "\\u0026"),
        (" ", "\\u2028"),
        (" ", "\\u2029"),
    ):
        text = text.replace(raw, escaped)
    return markupsafe.Markup(text)


def breadcrumbs(page: Page, by_path: dict) -> list[dict]:
    chain, current = [], page
    while current is not None:
        chain.append({"name": current.breadcrumb_name, "path": current.path})
        current = by_path.get(current.parent) if current.parent else None
    return list(reversed(chain))


def structured_data(
    page: Page, crumbs: list[dict], config: SiteConfig, site: dict
) -> list:
    url = config.absolute(page.path)
    blocks = []
    if page.path == "/":
        blocks.append(
            {
                "@context": "https://schema.org",
                "@type": "WebSite",
                "name": site["site_name"],
                "url": url,
            }
        )
    elif page.kind in ("question", "edition"):
        article = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": page.title,
            "description": page.description,
            "url": url,
            "mainEntityOfPage": url,
            "inLanguage": site["language"],
        }
        for key, field in (
            ("date_published", "datePublished"),
            ("date_modified", "dateModified"),
        ):
            if page.meta.get(key):
                article[field] = page.meta[key]
        if page.meta["authors"]:
            article["author"] = [
                {"@type": "Person", **author} for author in page.meta["authors"]
            ]
        blocks.append(article)
    else:
        blocks.append(
            {
                "@context": "https://schema.org",
                "@type": (
                    "CollectionPage"
                    if page.kind in ("hub", "directory")
                    else "WebPage"
                ),
                "name": page.title,
                "description": page.description,
                "url": url,
            }
        )
    if len(crumbs) >= 2:
        blocks.append(
            {
                "@context": "https://schema.org",
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": i,
                        "name": crumb["name"],
                        "item": config.absolute(crumb["path"]),
                    }
                    for i, crumb in enumerate(crumbs, start=1)
                ],
            }
        )
    return [json_ld(block) for block in blocks]


# ---------------------------------------------------------------------------
# Rendering


def _environment() -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(TEMPLATE_DIR),
        autoescape=True,
        undefined=jinja2.StrictUndefined,
        keep_trailing_newline=True,
    )


def _date_text(value: str | None) -> str | None:
    if not value:
        return None
    moment = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    moment = moment.astimezone(datetime.timezone.utc)
    return f"{moment.day} {moment:%B %Y}"


def _answer_view(meta: dict) -> dict:
    return {
        "revision": meta["answer_revision"],
        "basis_text": (
            "the measurement method and source code only; it states no"
            " measured values"
            if meta["answer_basis"] == "methodology"
            else "a review of dataset"
            f" {meta['answer_reviewed_dataset_sha256'][:12]}…"
        ),
        "date_published": meta.get("date_published"),
        "date_published_text": _date_text(meta.get("date_published")),
        "date_modified": meta.get("date_modified"),
        "date_modified_text": _date_text(meta.get("date_modified")),
    }


STAGING_LABEL = "Staging preview, not yet published"


def _edition_label(item: Published) -> str:
    if not item.route.startswith("/reports/"):
        return STAGING_LABEL
    suffix = item.route.rsplit("/", 1)[-1]
    revision = f", {suffix}" if re.match(r"^r\d+$", suffix) else ""
    return f"{_date_text(item.published_at)} edition{revision}"


def _edition_link(item: Published) -> dict:
    return {
        "path": item.route,
        "label": _edition_label(item),
        "date": item.published_at,
        "h1": item.edition.page.h1,
        "summary": item.edition.summary,
        "what_changed": item.edition.what_changed,
        "revision": item.edition.page.meta["answer_revision"],
    }


def _question_pages(
    question: Question, items: list[Published], *, preview: bool = False
) -> list[Page]:
    """The stable question page (latest edition) and one page per edition."""
    items = sorted(items, key=lambda i: i.published_at)
    latest = items[-1]
    history = [_edition_link(i) for i in reversed(items)]
    hub_meta = {
        **latest.edition.page.meta,
        "date_published": items[0].published_at,
        "date_modified": latest.published_at if len(items) > 1 else None,
    }
    pages = [
        dataclasses.replace(
            latest.edition.page,
            path=question.path,
            breadcrumb_name=question.breadcrumb_name,
            parent="/questions",
            meta=hub_meta,
            extra={
                "history": history,
                "updated": history[0] if len(items) > 1 else None,
                "related_metrics": question.related_metrics,
                "category": question.category,
                # Real publication time (a dated, archived route); a
                # staging preview has none, so no date is shown.
                "verified_date": not preview
                and latest.route.startswith("/reports/"),
            },
        )
    ]
    for index, item in enumerate(items):
        if item.route == question.path:
            continue  # staging: no dated edition page
        page = item.edition.page
        label = _edition_label(item)
        pages.append(
            dataclasses.replace(
                page,
                kind="edition",
                path=item.route,
                title=f"{page.title} ({label})",
                description=f"{label} of this answer: {item.edition.summary}"[
                    :300
                ],
                breadcrumb_name=label,
                parent=question.path,
                canonical_path=question.path,
                meta={**page.meta, "date_published": item.published_at},
                extra={
                    "edition": _edition_link(item),
                    "earlier": [
                        _edition_link(i) for i in reversed(items[:index])
                    ],
                    "current_path": question.path,
                    "frozen": item.frozen,
                },
            )
        )
    return pages


def plan_site(
    config: SiteConfig,
    dataset: Dataset | None = None,
    content_dir: pathlib.Path = CONTENT_DIR,
    *,
    archive_dir: pathlib.Path | None = None,
    freeze_at: str | None = None,
    preview_at: str | None = None,
    staging: bool = False,
    provisional: bool = False,
    costs: dict | None = None,
    forbidden: tuple[str, ...] = (),
) -> tuple[dict[str, bytes], dict[str, bytes], dict | None, list[Page]]:
    """Renders and checks the whole site without writing anything.

    Returns:
        (output files, archive files to create, new manifest or None,
        every page).
    """
    if freeze_at and preview_at:
        raise SiteError("A preview can never be frozen.")
    if staging and not preview_at:
        raise SiteError("A staging build needs a preview time.")
    for moment in (freeze_at, preview_at):
        if moment is not None and not _PUBLISHED_AT_RE.match(moment):
            raise SiteError(
                "Publication time must be UTC YYYY-MM-DDTHH:MM:SSZ."
            )
    archive_dir = (
        content_dir / "archive" if archive_dir is None else archive_dir
    )
    site, base_pages, questions = load_pages(content_dir)
    published, new_entries = plan_editions(
        questions,
        config,
        archive_dir,
        freeze_at=freeze_at,
        preview_at=preview_at,
        staging=staging,
    )
    if dataset is not None:
        for page in base_pages:
            if page.kind == "metric":
                validate_summary(
                    dataset.summary, page.meta.get("expected_population")
                )
    if dataset is not None:
        dataset = _provisional_gate(dataset, provisional, staging)
    data = data_view(dataset) if dataset is not None else None
    real_data = dataset is not None and dataset.source == "real"
    banner = None
    if staging:
        banner = (
            "Staging preview.",
            "This temporary site is not published and may change.",
        )
    elif preview_at:
        banner = (
            "Draft preview.",
            "These pages are not published and may change.",
        )
    elif data and data["source"] == "synthetic":
        banner = (
            "Synthetic test data.",
            "The numbers in this build are not real measurements.",
        )
    pages = list(base_pages)
    hubs = {}
    for question in questions:
        items = [p for p in published if p.question is question]
        if items:
            question_pages = _question_pages(
                question, items, preview=preview_at is not None
            )
            hubs[question.question_id] = question_pages[0]
            pages.extend(question_pages)
    evidence = []
    if data is not None and data.get("provisional"):
        for question in questions:
            if question.question_id in hubs or not question.related_metrics:
                continue
            page = _evidence_page(question)
            evidence.append(page)
            pages.append(page)
    listing = _question_listing(
        questions, published, hubs, preview=preview_at is not None
    ) + [
        {
            "question_id": None,
            "path": page.path,
            "h1": page.h1,
            "summary": page.extra["summary"],
            "category": page.extra["category"],
            "date": None,
            "date_text": None,
            "updated": False,
            "sort": "",
        }
        for page in evidence
    ]
    home = next(p for p in pages if p.kind == "home")
    pages[pages.index(home)] = home = dataclasses.replace(
        home, extra={**home.extra, "pager": _pager(1, len(listing))}
    )
    for number in range(2, _page_count(len(listing)) + 1):
        pages.append(
            dataclasses.replace(
                home,
                path=f"/page/{number}",
                title=f"{home.title} (page {number})",
                description=f"Questions, newest first: page {number}."
                f" {home.description}"[:300],
                sections=(),
                extra={"pager": _pager(number, len(listing))},
            )
        )
    by_path = {page.path: page for page in pages}
    directory = [
        {
            "path": q.path,
            "h1": hubs[q.question_id].h1,
            "description": hubs[q.question_id].description,
            "editions": hubs[q.question_id].extra["history"],
        }
        for q in questions
        if q.question_id in hubs
    ]
    methodology = {}
    for question in questions:
        for metric_path in question.related_metrics:
            if (
                metric_path not in by_path
                or by_path[metric_path].kind != "metric"
            ):
                raise SiteError(
                    f"{question.question_id}: unknown related metric"
                    f" {metric_path}."
                )
            if question.question_id in hubs:
                methodology.setdefault(metric_path, hubs[question.question_id])
    environment = _environment()
    nav = [
        {"path": "/questions", "label": "Questions"},
        {"path": "/llm-performance", "label": "Metrics"},
        {"path": "/costs", "label": "Costs"},
    ]
    files, frozen_paths = {}, set()
    for page in pages:
        if page.kind == "edition" and page.extra["frozen"] is not None:
            # Published history is served byte-for-byte, never re-rendered.
            files[page.output_file] = page.extra["frozen"]
            frozen_paths.add(page.path)
            continue
        robots = None
        if (
            banner
            or (page.kind == "metric" and not real_data)
            or (page.kind == "costs" and costs is None)
        ):
            # Empty or synthetic metric and cost pages are not indexable
            # content; educational pages stay indexable without any data.
            robots = "noindex, nofollow" if preview_at else "noindex"
        page = dataclasses.replace(page, robots=robots)
        by_path[page.path] = page
        crumbs = breadcrumbs(page, by_path)
        view = {
            "kind": page.kind,
            "path": page.path,
            "title": page.title,
            "h1": page.h1,
            "description": page.description,
            "canonical": config.absolute(page.canonical),
            "og_type": "article"
            if page.kind in ("question", "edition")
            else "website",
            "breadcrumbs": crumbs,
            "json_ld": structured_data(page, crumbs, config, site),
            "robots": robots,
        }
        if page.kind == "hub":
            links = list(hubs.values()) + [
                p for p in base_pages if p.kind == "metric"
            ]
        else:
            links = []
        html_text = environment.get_template("page.html").render(
            site={"name": site["site_name"], "language": site["language"]},
            page=view,
            sections=page.sections,
            answer=_answer_view(page.meta)
            if page.kind in ("question", "edition")
            else None,
            extra=page.extra,
            links=[
                {"path": p.path, "h1": p.h1, "description": p.description}
                for p in links
            ],
            feed=_page_slice(listing, page.extra["pager"])
            if page.kind == "home"
            else [],
            related=_related(page, listing) if page.kind == "question" else [],
            directory=directory if page.kind == "directory" else [],
            categories=_by_category(listing)
            if page.kind == "directory"
            else [],
            # Editions are immutable, so they never embed changing numbers.
            data=None if page.kind == "edition" else data,
            setup=setup_rows(),
            related_metric=page.meta.get("related_metric") or page.path,
            methodology_page=methodology.get(page.path),
            methodology_version=METHODOLOGY_VERSION,
            banner=banner,
            nav=nav,
            costs=costs,
            csp=CSP,
            stylesheet=STYLESHEET_PATH,
        )
        files[page.output_file] = html_text.encode("utf-8")
    files[STYLESHEET_PATH[1:]] = STYLESHEET_SOURCE.read_bytes()
    if dataset is not None:
        files[dataset.json_path[1:]] = dataset.public_bytes
    redirects = [
        {"from": source, "to": q.path, "status": 301}
        for q in questions
        if q.question_id in hubs
        for source in (f"{q.path}-latest", *q.aliases)
    ]
    for rule in redirects:
        if _route_exists(rule["from"], files) or not _route_exists(
            rule["to"], files
        ):
            raise SiteError(
                f"Redirect {rule['from']} collides or has no target."
            )
    files["redirects.json"] = _canonical_json({"redirects": redirects})
    files.update(
        hosting_files(
            config,
            [
                dataclasses.replace(p, robots=_robots_of(p, files))
                for p in pages
            ],
            redirects,
            published,
            environment.get_template("404.html").render(
                site={"name": site["site_name"], "language": site["language"]},
                nav=nav,
                csp=CSP,
                stylesheet=STYLESHEET_PATH,
            ),
            staging=preview_at is not None,
        )
    )
    check_site(files, config, pages, frozen_paths)
    scan_public(files, forbidden)
    archive_files, manifest = {}, None
    if new_entries:
        manifest = load_manifest(archive_dir)
        manifest = {
            **manifest,
            "editions": manifest["editions"]
            + [
                {
                    **entry,
                    "html_sha256": hashlib.sha256(
                        files[f"{entry['route'][1:]}/index.html"]
                    ).hexdigest(),
                }
                for entry in new_entries
            ],
        }
        for entry in new_entries:
            name = f"{entry['route'][1:]}/index.html"
            archive_files[name] = files[name]
    return dict(sorted(files.items())), archive_files, manifest, pages


def _evidence_page(question: Question) -> Page:
    """Measured values for a question whose written answer is a draft.

    Only the question itself and generated data are shown; the draft's
    answer prose is never published.
    """
    draft = question.editions[-1].page
    return Page(
        kind=EVIDENCE_KIND,
        path=question.path,
        title=f"{draft.h1} Measured values"[:120],
        h1=draft.h1,
        description=(
            "Measured values only, from our provisional OpenAI pilot data;"
            " the written answer to this question is not yet approved."
        ),
        breadcrumb_name=question.breadcrumb_name,
        sections=(
            Section("evidence", None, None, "evidence"),
            Section("measured", "Measured values", None, "measurements"),
        ),
        meta={"related_metric": question.related_metrics[0]},
        parent="/questions",
        extra={
            "category": question.category,
            "summary": "Measured values from our OpenAI pilot (provisional);"
            " the written answer is not yet approved.",
        },
    )


def _page_count(total: int) -> int:
    """Home pages needed; an empty site still has its first page."""
    return max(1, -(-total // QUESTIONS_PER_PAGE))


def _pager(number: int, total: int) -> dict:
    """Previous/next links for home page `number` (no empty pages)."""
    count = _page_count(total)

    def path(n):
        return "/" if n == 1 else f"/page/{n}"

    return {
        "number": number,
        "count": count,
        "previous": path(number - 1) if number > 1 else None,
        "next": path(number + 1) if number < count else None,
    }


def _page_slice(listing: list[dict], pager: dict) -> list[dict]:
    start = (pager["number"] - 1) * QUESTIONS_PER_PAGE
    return listing[start : start + QUESTIONS_PER_PAGE]


def _question_listing(
    questions: list[Question],
    published: list[Published],
    hubs: dict,
    *,
    preview: bool = False,
) -> list[dict]:
    """Every published question, newest first (latest edition time).

    A date is shown only when it is a real publication time, i.e. the
    latest edition has a dated route outside a preview; previews show none.
    """
    rows = []
    for question in questions:
        if question.question_id not in hubs:
            continue
        items = [p for p in published if p.question is question]
        latest = max(items, key=lambda i: i.published_at)
        verified = not preview and latest.route.startswith("/reports/")
        rows.append(
            {
                "question_id": question.question_id,
                "path": question.path,
                "h1": hubs[question.question_id].h1,
                "summary": latest.edition.summary,
                "category": question.category,
                "date": latest.published_at if verified else None,
                "date_text": _date_text(latest.published_at)
                if verified
                else None,
                "updated": verified and len(items) > 1,
                "sort": latest.published_at,
            }
        )
    rows.sort(key=lambda r: (r["sort"], r["question_id"]), reverse=True)
    return rows


def _by_category(listing: list[dict]) -> list[dict]:
    """The directory: questions grouped by category, A to Z within each."""
    groups = []
    for name in (*CATEGORIES, None):
        rows = sorted(
            (r for r in listing if r["category"] == name),
            key=lambda r: r["h1"].lower(),
        )
        if rows:
            groups.append({"name": name or "Other questions", "rows": rows})
    return groups


def _related(page: Page, listing: list[dict], limit: int = 5) -> list[dict]:
    """Other published questions, same category first, newest first."""
    own = next((r for r in listing if r["path"] == page.path), None)
    others = [r for r in listing if r["path"] != page.path]
    if own is not None and own["category"]:
        others.sort(key=lambda r: r["category"] != own["category"])
    return others[:limit]


def _robots_of(page: Page, files: dict) -> str | None:
    robots = parse_page(files[page.output_file]).meta.get("robots")
    return robots[0] if robots else None


def hosting_files(
    config: SiteConfig,
    pages: list[Page],
    redirects: list[dict],
    published: list[Published],
    not_found_html: str,
    *,
    staging: bool = False,
) -> dict[str, bytes]:
    """`sitemap.xml`, `robots.txt`, `_redirects`, `_headers`, `404.html`.

    The sitemap lists only indexable canonical pages, never dated editions
    (canonical to their question), redirects, drafts or noindex pages.
    `lastmod` is given only where a real change time exists: a question's
    latest publication, and the feed pages' newest publication. A rebuild
    never advances it.
    """
    latest = {}
    for item in published:
        path = item.question.path
        latest[path] = max(latest.get(path, ""), item.published_at)
    newest = max(latest.values(), default=None)
    entries = []
    for page in pages:
        if page.kind == "edition" or page.robots:
            continue
        lastmod = latest.get(page.path)
        if page.path in ("/", "/questions"):
            lastmod = newest
        entries.append((config.absolute(page.path), lastmod))
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for url, lastmod in sorted(entries):
        lines.append(
            f"<url><loc>{xml_escape(url)}</loc>"
            + (f"<lastmod>{lastmod}</lastmod>" if lastmod else "")
            + "</url>"
        )
    lines.append("</urlset>")
    # Header rules mirror the meta CSP (the HTTP header also covers
    # frame-ancestors, which a meta tag cannot).
    headers = "\n".join(
        [
            "/*",
            f"  Content-Security-Policy: {CSP}; frame-ancestors 'none'",
            "  X-Content-Type-Options: nosniff",
            "  Referrer-Policy: strict-origin-when-cross-origin",
            "  Permissions-Policy: camera=(), microphone=(), geolocation=()",
            # A preview/staging deployment (e.g. on *.workers.dev) must
            # never be indexed, whatever hostname serves it.
            *(["  X-Robots-Tag: noindex, nofollow"] if staging else []),
            "",
        ]
    )
    return {
        "sitemap.xml": ("\n".join(lines) + "\n").encode("utf-8"),
        "robots.txt": (
            "User-agent: *\nAllow: /\n"
            + (
                ""
                if staging
                else f"\nSitemap: {config.absolute('/sitemap.xml')}\n"
            )
        ).encode("utf-8"),
        "_redirects": "".join(
            f"{rule['from']} {rule['to']} {rule['status']}\n"
            for rule in redirects
        ).encode("utf-8"),
        "_headers": headers.encode("utf-8"),
        "404.html": not_found_html.encode("utf-8"),
    }


def xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# Strings that must never appear in public output: private storage, keys,
# provider request ids, private ledger references (added per build).
_FORBIDDEN = (
    "gs://",
    "llm-metrics-513617-results",
    "storage.googleapis.com",
    "OPENAI_API_KEY",
    "private_reference",
    "synthetic-req-",
)
_FORBIDDEN_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}|\breq_[A-Za-z0-9]{8,}")


def scan_public(files: dict, extra: tuple[str, ...] = ()) -> None:
    """Refuses the build if any public file contains forbidden content."""
    for name, data in files.items():
        text = data.decode("utf-8", errors="replace")
        for needle in (*_FORBIDDEN, *extra):
            if needle and needle in text:
                raise SiteError(f"Forbidden content in public file {name}.")
        if _FORBIDDEN_RE.search(text):
            raise SiteError(
                f"Key or provider request id in public file {name}."
            )


def resolve(files: dict, request_path: str) -> tuple[int, str | None]:
    """Emulates the chosen host: Cloudflare Workers Static Assets with
    `html_handling: "drop-trailing-slash"`, `not_found_handling: "404-page"`
    and `_redirects` (per Cloudflare's published routing tables; to be
    confirmed on the real host before production).

    Returns:
        (status, Location for redirects or the served file name).
    """
    for line in files.get("_redirects", b"").decode().splitlines():
        source, target, status = line.split()
        if request_path == source:
            return int(status), target
    if request_path.endswith("/index.html"):
        return 307, request_path[: -len("/index.html")] or "/"
    if request_path.endswith(".html") and request_path != "/404.html":
        return 307, request_path[: -len(".html")]
    if request_path != "/" and request_path.endswith("/"):
        target = request_path.rstrip("/")
        if f"{target[1:]}/index.html" in files or target[1:] in files:
            return 307, target
    name = "index.html" if request_path == "/" else request_path[1:]
    if name in files and not name.startswith("_"):
        return 200, name
    if f"{name}/index.html" in files:
        return 200, f"{name}/index.html"
    return 404, "404.html"


def render_site(
    config: SiteConfig,
    dataset: Dataset | None = None,
    content_dir: pathlib.Path = CONTENT_DIR,
    **options,
) -> dict[str, bytes]:
    """Renders every page. Returns output path -> bytes (deterministic)."""
    return plan_site(config, dataset, content_dir, **options)[0]


def freeze(
    archive_dir: pathlib.Path, archive_files: dict, manifest: dict
) -> None:
    """Adds newly published editions to the archive, create-only.

    Pages are written before the manifest that lists them, so an
    interruption leaves at worst unlisted pages, which a re-run of the same
    freeze adopts only if byte-identical. Existing pages are never touched.
    """
    for name, data in archive_files.items():
        path = archive_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(path, "xb") as handle:
                handle.write(data)
        except FileExistsError:
            if path.read_bytes() != data:
                raise SiteError(
                    f"Archive already holds different bytes: {name}"
                ) from None
    temporary = archive_dir / f".{MANIFEST_NAME}.tmp"
    temporary.write_bytes(_canonical_json(manifest))
    os.replace(temporary, archive_dir / MANIFEST_NAME)


# ---------------------------------------------------------------------------
# Checks on the generated HTML


class PageParser(html.parser.HTMLParser):
    """Extracts the facts the checks and tests need from one page."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lang = None
        self.title = ""
        self.meta = {}
        self.links_rel = {}
        self.headings = []
        self.hrefs = []
        self.scripts = []
        self.breadcrumb = []
        self.paragraphs = []
        self._stack = []
        self._text = None
        self._in_breadcrumb = False
        self._crumb = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag not in _VOID_TAGS:
            self._stack.append(tag)
        if tag == "html":
            self.lang = attributes.get("lang")
        elif tag == "meta":
            key = (
                attributes.get("name")
                or attributes.get("property")
                or attributes.get("http-equiv")
            )
            if key:
                self.meta.setdefault(key, []).append(attributes.get("content"))
            if "charset" in attributes:
                self.meta["charset"] = [attributes["charset"]]
        elif tag == "link":
            self.links_rel.setdefault(attributes.get("rel"), []).append(
                attributes.get("href")
            )
        elif tag == "a":
            self.hrefs.append(attributes.get("href"))
            if self._in_breadcrumb:
                self._crumb = {"path": attributes.get("href"), "name": ""}
        elif tag == "nav" and attributes.get("aria-label") == "Breadcrumb":
            self._in_breadcrumb = True
        elif tag == "script":
            self.scripts.append({"type": attributes.get("type"), "text": ""})
        if tag in ("title", "h1", "h2", "h3", "h4", "p", "script"):
            self._text = []

    def handle_endtag(self, tag):
        if self._stack and self._stack[-1] == tag:
            self._stack.pop()
        text = "".join(self._text or [])
        if tag == "title" and "svg" not in self._stack:
            self.title = text
        elif tag in ("h1", "h2", "h3", "h4"):
            self.headings.append((int(tag[1]), text.strip()))
        elif tag == "p":
            self.paragraphs.append(" ".join(text.split()))
        elif tag == "script":
            self.scripts[-1]["text"] = text
        elif tag == "a" and self._crumb is not None:
            self.breadcrumb.append(self._crumb)
            self._crumb = None
        elif tag == "nav":
            self._in_breadcrumb = False
        if tag in ("title", "h1", "h2", "h3", "h4", "p", "script"):
            self._text = None

    def handle_data(self, data):
        if self._text is not None:
            self._text.append(data)
        if self._crumb is not None:
            self._crumb["name"] += data


def parse_page(data: bytes) -> PageParser:
    parser = PageParser()
    parser.feed(data.decode("utf-8"))
    parser.close()
    return parser


def _route_exists(href: str, files: dict) -> bool:
    path = href.split("#", 1)[0]
    if path == "/":
        return "index.html" in files
    return f"{path[1:]}/index.html" in files or path[1:] in files


def check_site(
    files: dict,
    config: SiteConfig,
    pages: list[Page],
    frozen_paths: set = frozenset(),
) -> None:
    """Hard checks on every generated page; any failure stops the build.

    Archived (frozen) editions are only checked for links that still
    resolve: their metadata was checked when they were published.
    """
    for page in pages:
        parsed = parse_page(files[page.output_file])
        where = page.path

        def require(condition, message, where=where):
            if not condition:
                raise SiteError(f"Page {where}: {message}")

        if page.path in frozen_paths:
            for href in parsed.hrefs:
                if href.startswith("/"):
                    require(_route_exists(href, files), f"broken link {href}")
            continue
        canonical = config.absolute(page.canonical)
        own_url = config.absolute(page.path)
        require(parsed.lang == "en", "missing lang")
        require(parsed.meta.get("charset") == ["utf-8"], "missing charset")
        require(
            parsed.meta.get("viewport")
            == ["width=device-width, initial-scale=1"],
            "missing viewport",
        )
        require(parsed.title == page.title, "title mismatch")
        require(
            parsed.meta.get("description") == [page.description],
            "description mismatch",
        )
        require(
            parsed.links_rel.get("canonical") == [canonical],
            "canonical mismatch",
        )
        require(parsed.meta.get("og:url") == [canonical], "og:url mismatch")
        require(
            parsed.meta.get("og:title") == [page.title], "og:title mismatch"
        )
        require("og:image" not in parsed.meta, "no image is defined")
        levels = [level for level, _ in parsed.headings]
        require(
            levels.count(1) == 1 and levels[0] == 1,
            "needs exactly one leading H1",
        )
        require(
            all(b - a <= 1 for a, b in zip(levels, levels[1:])),
            "heading levels skip",
        )
        require(
            all(s["type"] == "application/ld+json" for s in parsed.scripts),
            "executable script",
        )
        for href in parsed.hrefs:
            require(isinstance(href, str) and href, "empty link")
            if href.startswith("/"):
                require(
                    _route_exists(href, files), f"broken internal link {href}"
                )
            elif href.startswith("#"):
                require(
                    f'id="{href[1:]}"'.encode() in files[page.output_file],
                    f"missing anchor {href}",
                )
            else:
                require(href.startswith("https://"), f"non-https link {href}")
        blocks = [json.loads(s["text"]) for s in parsed.scripts]
        crumbs = [b for b in blocks if b.get("@type") == "BreadcrumbList"]
        visible = [
            (c["name"], config.absolute(c["path"])) for c in parsed.breadcrumb
        ]
        if page.kind == "home":
            require(not crumbs and not visible, "home has no breadcrumb trail")
        else:
            require(
                len(crumbs) == 1 and len(visible) >= 2, "breadcrumbs missing"
            )
            listed = [
                (i["name"], i["item"]) for i in crumbs[0]["itemListElement"]
            ]
            positions = [i["position"] for i in crumbs[0]["itemListElement"]]
            require(
                listed == visible,
                "BreadcrumbList differs from visible breadcrumbs",
            )
            require(
                positions == list(range(1, len(listed) + 1)),
                "breadcrumb positions",
            )
            require(
                listed[-1][1] == own_url, "last breadcrumb is not this page"
            )
        if page.kind in ("question", "edition"):
            articles = [b for b in blocks if b.get("@type") == "Article"]
            require(len(articles) == 1, "needs one Article")
            require(
                articles[0]["url"]
                == own_url
                == articles[0]["mainEntityOfPage"],
                "Article URL",
            )
            require(articles[0]["headline"] == page.title, "Article headline")
            related = page.meta.get("related_metric")
            require(
                related is None or related in parsed.hrefs,
                "no link to its metric page",
            )
            require(
                bool(page.meta.get("date_published")),
                "a published article needs its publication date",
            )
        if page.kind == "edition":
            require(
                page.extra["current_path"] in parsed.hrefs,
                "an edition must link to the current answer",
            )


# ---------------------------------------------------------------------------
# Yoast-inspired editorial report (advisory, never a ranking promise)


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9'’-]*", text)


def editorial_report(files: dict, pages: list[Page]) -> list[dict]:
    """Pass/warn/manual findings per question page; advisory only.

    Simple keyword and length heuristics cannot establish search quality;
    they flag things a reviewer should look at.
    """
    findings = []
    for page in pages:
        if page.kind != "question":
            continue
        parsed = parse_page(files[page.output_file])
        phrase = page.meta.get("focus_keyphrase", "").lower()
        intro = next((p for p in parsed.paragraphs if len(p) > 80), "")

        def add(check, ok, detail, page=page):
            findings.append(
                {
                    "page": page.path,
                    "check": check,
                    "status": "pass" if ok else "warn",
                    "detail": detail,
                }
            )

        for label, text in (
            ("title", page.title),
            ("h1", page.h1),
            ("meta description", page.description),
            ("introduction", intro),
        ):
            add(
                f"keyphrase in {label}",
                phrase in text.lower(),
                f"focus keyphrase {phrase!r}",
            )
        slug_words = set(page.path.strip("/").split("-"))
        terms = page.meta.get("slug_terms", [])
        add(
            "slug terms",
            bool(terms) and set(terms) <= slug_words,
            f"slug {page.path} contains {terms}",
        )
        add(
            "title length",
            len(page.title) <= 60,
            f"{len(page.title)} characters (≤ 60 avoids truncation)",
        )
        add(
            "meta description length",
            120 <= len(page.description) <= 160,
            f"{len(page.description)} characters (120–160 suggested)",
        )
        h2s = [text for level, text in parsed.headings if level == 2]
        add(
            "keyphrase or topic in a subheading",
            any(
                word in " ".join(h2s).lower()
                for word in (*page.meta.get("slug_terms", []), phrase)
            ),
            f"{len(h2s)} H2 subheadings",
        )
        body = " ".join(parsed.paragraphs)
        words = _words(body)
        occurrences = body.lower().count(phrase) if phrase else 0
        density = occurrences * len(_words(phrase)) / max(len(words), 1)
        add(
            "keyphrase density",
            0 < density <= 0.03,
            f"{occurrences} uses in {len(words)} words ({density:.1%});"
            " >3% suggests stuffing",
        )
        long_paragraphs = [p for p in parsed.paragraphs if len(_words(p)) > 150]
        add(
            "paragraph length",
            not long_paragraphs,
            f"{len(long_paragraphs)} paragraphs over 150 words",
        )
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", body) if _words(s)]
        long_sentences = [s for s in sentences if len(_words(s)) > 20]
        share = len(long_sentences) / max(len(sentences), 1)
        add(
            "sentence length",
            share <= 0.25,
            f"{share:.0%} of {len(sentences)} sentences over 20 words"
            " (≤ 25% suggested)",
        )
        internal = [h for h in parsed.hrefs if h.startswith("/")]
        add(
            "internal links",
            len(set(internal)) >= 2,
            f"{len(set(internal))} distinct internal links",
        )
        add(
            "outbound links",
            any(h.startswith("https://") for h in parsed.hrefs),
            "links to source code",
        )
        findings.append(
            {
                "page": page.path,
                "check": "readability and intent",
                "status": "manual",
                "detail": (
                    "A reviewer must confirm the answer is accurate, answers"
                    " the question first and reads naturally."
                ),
            }
        )
        findings.append(
            {
                "page": page.path,
                "check": "structured data",
                "status": "manual",
                "detail": (
                    "Validated offline; check with the Rich Results Test once"
                    " hosted."
                ),
            }
        )
    return findings


# ---------------------------------------------------------------------------
# Output


def write_site(output: pathlib.Path, files: dict) -> None:
    """Writes the site to `output`, replacing only a previous site build.

    The new tree is built in a sibling temporary directory and moved into
    place, so `output` holds either the old or the new complete build.
    """
    output = pathlib.Path(output)
    if output.is_symlink():
        raise SiteError("Output must not be a symlink.")
    resolved = output.resolve()
    if resolved.is_relative_to(PACKAGE_DIR.resolve()):
        raise SiteError("Output must not be inside the llm_metrics package.")
    if output.exists() and not (output / BUILD_MARKER).is_file():
        raise SiteError(
            "Output exists and is not a previous site build; choose an empty"
            " path."
        )
    parent = resolved.parent
    if not parent.is_dir():
        raise SiteError(f"Output parent directory does not exist: {parent}")
    staging = pathlib.Path(
        tempfile.mkdtemp(dir=parent, prefix=f".{output.name}.")
    )
    try:
        for name, data in files.items():
            target = staging / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        (staging / BUILD_MARKER).write_text("llm-metrics static site build\n")
        retired = None
        if output.exists():
            retired = parent / f".{output.name}.old-{os.getpid()}"
            os.rename(resolved, retired)
        os.rename(staging, resolved)
        staging = None
        if retired is not None:
            shutil.rmtree(retired)
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)


def build(
    output: pathlib.Path,
    site_url: str,
    analytics: pathlib.Path | None = None,
    data_source: str | None = None,
    content_dir: pathlib.Path = CONTENT_DIR,
    *,
    archive_dir: pathlib.Path | None = None,
    freeze_at: str | None = None,
    preview_at: str | None = None,
    staging: bool = False,
    provisional: bool = False,
    cost_ledger_path: pathlib.Path | None = None,
) -> tuple[dict, list[dict], list[str]]:
    """Validates, renders and checks everything, then writes.

    Order: the whole site is built and checked in memory first; then newly
    published editions are added to the archive (create-only); the output
    directory is replaced last, so a failure at any point leaves the
    previous output and archive intact.

    Returns:
        (files, editorial report findings, newly published routes).
    """
    config = SiteConfig(site_url)
    archive_dir = (
        content_dir / "archive" if archive_dir is None else archive_dir
    )
    _, base_pages, _ = load_pages(content_dir)
    dataset = None
    if analytics is not None:
        expected = next(p for p in base_pages if p.kind == "metric").meta[
            "expected_population"
        ]
        dataset = load_dataset(analytics, data_source, expected)
    costs, forbidden = None, ()
    if cost_ledger_path is not None:
        try:
            ledger = cost_ledger.load(cost_ledger_path)
        except cost_ledger.LedgerError as error:
            raise SiteError(f"Cost ledger: {error}") from None
        costs = cost_ledger.summarize(ledger.data)
        forbidden = tuple(
            e["private_reference"]
            for e in ledger.data["entries"]
            if e.get("private_reference")
        )
    files, archive_files, manifest, pages = plan_site(
        config,
        dataset,
        content_dir,
        archive_dir=archive_dir,
        freeze_at=freeze_at,
        preview_at=preview_at,
        staging=staging,
        provisional=provisional,
        costs=costs,
        forbidden=forbidden,
    )
    if manifest is not None:
        freeze(archive_dir, archive_files, manifest)
    write_site(output, files)
    published = sorted(
        "/" + name.removesuffix("/index.html") for name in archive_files
    )
    return files, editorial_report(files, pages), published


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m llm_metrics.static_site",
        description="Build the static question and metric pages locally.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--output", required=True, help="site directory to (re)build"
    )
    parser.add_argument(
        "--site-url",
        required=True,
        help="canonical base, e.g. https://llmxchange.com",
    )
    parser.add_argument(
        "--analytics", help="llm-metrics.analytics.v1 summary (optional)"
    )
    parser.add_argument(
        "--data-source",
        choices=DATA_SOURCES,
        help="required with --analytics: is the dataset real or synthetic?",
    )
    parser.add_argument(
        "--report", help="also write the editorial report JSON here"
    )
    parser.add_argument(
        "--cost-ledger",
        help="private llm-metrics.cost-ledger.v1 file (never published)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--publish-at",
        help="publish approved, unarchived editions at this UTC time"
        " (YYYY-MM-DDTHH:MM:SSZ) and freeze them into the archive",
    )
    mode.add_argument(
        "--preview-at",
        help="show every unarchived edition, drafts included, at this UTC"
        " time for review; noindex and never archived",
    )
    parser.add_argument(
        "--provisional-metrics",
        action="store_true",
        help="with --staging and a real dataset: allow a partial pilot"
        " window, clearly labelled provisional (never for production)",
    )
    parser.add_argument(
        "--staging",
        action="store_true",
        help="with --preview-at: approved editions only, on stable pages,"
        " with no dated edition pages (for a temporary public host)",
    )
    options = parser.parse_args(argv)
    if options.staging and not options.preview_at:
        parser.error("--staging requires --preview-at")
    if (options.analytics is None) != (options.data_source is None):
        parser.error("--analytics and --data-source must be given together")
    try:
        files, report, published = build(
            pathlib.Path(options.output),
            options.site_url,
            None
            if options.analytics is None
            else pathlib.Path(options.analytics),
            options.data_source,
            freeze_at=options.publish_at,
            preview_at=options.preview_at,
            staging=options.staging,
            provisional=options.provisional_metrics,
            cost_ledger_path=None
            if options.cost_ledger is None
            else pathlib.Path(options.cost_ledger),
        )
    except SiteError as error:
        print(f"Error: {error} Nothing written.", file=sys.stderr)
        return 1
    if options.report:
        pathlib.Path(options.report).write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", "utf-8"
        )
    pages = sum(name.endswith(".html") for name in files)
    data_label = (
        "no dataset"
        if options.analytics is None
        else f"{options.data_source} dataset"
    )
    print(f"Built {pages} pages into {options.output} ({data_label}).")
    for route in published:
        print(f"  Published and archived: {route}")
    for finding in report:
        print(
            f"  [{finding['status']:6}] {finding['page']}:"
            f" {finding['check']} — {finding['detail']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
