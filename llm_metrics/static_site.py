"""Deterministic static HTML site: question articles and metric pages.

Usage:
    python -m llm_metrics.static_site --output DIR --site-url https://HOST
        [--analytics SUMMARY.json --data-source real|synthetic]
        [--report REPORT.json]

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
PAGE_KINDS = ("home", "hub", "question", "metric")
GENERATED_SECTIONS = {
    "question": ("findings", "setup"),
    "metric": ("measurements", "setup", "provenance"),
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

    @property
    def output_file(self) -> str:
        return (
            "index.html" if self.path == "/" else f"{self.path[1:]}/index.html"
        )

    @property
    def parent(self) -> str | None:
        if self.kind == "home":
            return None
        return "/" if self.kind == "hub" else "/llm-performance"


@dataclasses.dataclass(frozen=True)
class Dataset:
    """A validated analytics summary and its identity."""

    summary: dict
    sha256: str
    data: bytes
    source: str  # "real" or "synthetic"

    @property
    def json_path(self) -> str:
        return f"/data/analytics/{self.sha256}.json"


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
    if not _PATH_RE.match(str(meta.get("related_metric"))):
        raise SiteError(f"{source}: related_metric must be a page path.")


def load_pages(
    content_dir: pathlib.Path = CONTENT_DIR,
) -> tuple[dict, list[Page]]:
    """Loads `site.json` and every listed page, in listed order."""
    try:
        site = json.loads((content_dir / "site.json").read_text("utf-8"))
    except (OSError, ValueError):
        raise SiteError(
            "site_content/site.json is missing or not JSON."
        ) from None
    pages = [
        _load_page(content_dir / entry, content_dir)
        for entry in site.get("pages", [])
    ]
    paths = [page.path for page in pages]
    if len(set(paths)) != len(paths):
        raise SiteError("Two pages share a path.")
    for field in ("title", "description", "h1"):
        values = [getattr(page, field) for page in pages]
        if len(set(values)) != len(values):
            raise SiteError(f"Page {field}s must be unique.")
    if [p.kind for p in pages].count(
        "home"
    ) != 1 or "/llm-performance" not in paths:
        raise SiteError(
            "The site needs one home page and the /llm-performance hub."
        )
    return site, pages


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
    if page.kind == "home":
        blocks.append(
            {
                "@context": "https://schema.org",
                "@type": "WebSite",
                "name": site["site_name"],
                "url": url,
            }
        )
    elif page.kind == "question":
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
                "@type": "CollectionPage" if page.kind == "hub" else "WebPage",
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


def render_site(
    config: SiteConfig,
    dataset: Dataset | None = None,
    content_dir: pathlib.Path = CONTENT_DIR,
) -> dict[str, bytes]:
    """Renders every page. Returns output path -> bytes (deterministic)."""
    site, pages = load_pages(content_dir)
    by_path = {page.path: page for page in pages}
    environment = _environment()
    metric_pages = [p for p in pages if p.kind == "metric"]
    for page in metric_pages:
        if dataset is not None:
            validate_summary(
                dataset.summary, page.meta.get("expected_population")
            )
    data = data_view(dataset) if dataset is not None else None
    files = {}
    for page in pages:
        crumbs = breadcrumbs(page, by_path)
        robots = "noindex" if data and data["source"] == "synthetic" else None
        view = {
            "kind": page.kind,
            "path": page.path,
            "title": page.title,
            "h1": page.h1,
            "description": page.description,
            "canonical": config.absolute(page.path),
            "og_type": "article" if page.kind == "question" else "website",
            "breadcrumbs": crumbs,
            "json_ld": structured_data(page, crumbs, config, site),
            "robots": robots,
        }
        answer = None
        if page.kind == "question":
            meta = page.meta
            answer = {
                "revision": meta["answer_revision"],
                "basis_text": (
                    "the measurement method only; it was not reviewed against"
                    " measured data"
                    if meta["answer_basis"] == "methodology"
                    else "a review of dataset"
                    f" {meta['answer_reviewed_dataset_sha256'][:12]}…"
                ),
                "date_published": meta.get("date_published"),
                "date_published_text": _date_text(meta.get("date_published")),
                "date_modified": meta.get("date_modified"),
                "date_modified_text": _date_text(meta.get("date_modified")),
            }
        if page.kind in ("home", "hub"):
            links = [p for p in pages if p.kind in ("question", "metric")]
            if page.kind == "home":
                links = [by_path["/llm-performance"], *links]
            links = [
                {"path": p.path, "h1": p.h1, "description": p.description}
                for p in links
            ]
        else:
            links = []
        html_text = environment.get_template("page.html").render(
            site={"name": site["site_name"], "language": site["language"]},
            page=view,
            sections=page.sections,
            answer=answer,
            links=links,
            data=data,
            setup=setup_rows(),
            related_metric=page.meta.get("related_metric", page.path),
            methodology_version=METHODOLOGY_VERSION,
            csp=CSP,
            stylesheet=STYLESHEET_PATH,
        )
        files[page.output_file] = html_text.encode("utf-8")
    files[STYLESHEET_PATH[1:]] = STYLESHEET_SOURCE.read_bytes()
    if dataset is not None:
        files[dataset.json_path[1:]] = dataset.data
    check_site(files, config, pages)
    return dict(sorted(files.items()))


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


def check_site(files: dict, config: SiteConfig, pages: list[Page]) -> None:
    """Hard checks on every generated page; any failure stops the build."""
    for page in pages:
        parsed = parse_page(files[page.output_file])
        where = page.path

        def require(condition, message, where=where):
            if not condition:
                raise SiteError(f"Page {where}: {message}")

        canonical = config.absolute(page.path)
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
                listed[-1][1] == canonical, "last breadcrumb is not this page"
            )
        if page.kind == "question":
            articles = [b for b in blocks if b.get("@type") == "Article"]
            require(len(articles) == 1, "needs one Article")
            require(
                articles[0]["url"]
                == canonical
                == articles[0]["mainEntityOfPage"],
                "Article URL",
            )
            require(articles[0]["headline"] == page.title, "Article headline")
            require(
                page.meta["related_metric"] in parsed.hrefs,
                "no link to its metric page",
            )
        if page.kind == "metric":
            methodology = page.meta.get("methodology_page")
            require(methodology in parsed.hrefs, "no link to its methodology")


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
                for word in ("measure", "ttft", phrase)
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
) -> tuple[dict, list[dict]]:
    """Validates, renders, checks and writes the site.

    Returns:
        (files, editorial report findings).
    """
    config = SiteConfig(site_url)
    _, pages = load_pages(content_dir)
    dataset = None
    if analytics is not None:
        expected = next(p for p in pages if p.kind == "metric").meta[
            "expected_population"
        ]
        dataset = load_dataset(analytics, data_source, expected)
    files = render_site(config, dataset, content_dir)
    write_site(output, files)
    return files, editorial_report(files, pages)


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
    options = parser.parse_args(argv)
    if (options.analytics is None) != (options.data_source is None):
        parser.error("--analytics and --data-source must be given together")
    try:
        files, report = build(
            pathlib.Path(options.output),
            options.site_url,
            None
            if options.analytics is None
            else pathlib.Path(options.analytics),
            options.data_source,
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
    for finding in report:
        print(
            f"  [{finding['status']:6}] {finding['page']}:"
            f" {finding['check']} — {finding['detail']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
