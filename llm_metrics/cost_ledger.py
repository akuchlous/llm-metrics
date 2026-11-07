"""Private, operator-reviewed project cost ledger -> sanitized public summary.

The ledger (schema `llm-metrics.cost-ledger.v1`) is a local JSON file the
operator writes from authorized billing exports and receipts. It is never
published and never read from a billing API: this module has no network or
credential access. Only `summarize()`'s output reaches the website.

"Cost" here means what the operator has actually been charged, across every
paid service of the project (LLM providers, Google Cloud, hosting, domain,
tools). It is not the benchmark's token-price estimate. Rules:

- Amounts are decimal strings, kept per currency; there is no FX conversion.
- Only `status: "charged"` entries count toward the verified subtotal.
  `invoiced_unpaid` is shown separately; `estimate` entries are never added
  to any charged figure (an estimate is not a charge, and adding it next to
  an invoice that already includes it would double-count).
- `net = charged_amount - refunds`. `charged_amount` is what was actually
  charged after credits and including tax; `credits` and `taxes` are shown
  for transparency only.
- A source with no entry is unknown, never $0.
- A lifetime total is shown only when every declared source is marked fully
  reconciled from the project start to the reporting cut-off and has no
  unpaid or estimated items; otherwise the public wording is "Full lifetime
  total not yet verified."
- `private_reference` (invoice, account or payment ids) is validated but
  never copied to the summary.

Overlapping charged periods for the same source, duplicate entry ids and
reused evidence hashes are refused as likely double counting.
"""

import dataclasses
import datetime
import decimal
import hashlib
import json
import pathlib
import re

SCHEMA_VERSION = "llm-metrics.cost-ledger.v1"
SUMMARY_SCHEMA = "llm-metrics.cost-summary.v1"
STATUSES = ("charged", "invoiced_unpaid", "estimate")
LIFETIME_UNVERIFIED = "Full lifetime total not yet verified."
MAX_LEDGER_BYTES = 1024 * 1024

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_AMOUNT_RE = re.compile(r"^\d+(\.\d{1,6})?$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class LedgerError(ValueError):
    """The ledger is invalid. Messages never include private references."""


@dataclasses.dataclass(frozen=True)
class Ledger:
    data: dict
    sha256: str


def _text(item: dict, key: str, where: str, limit: int = 200) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise LedgerError(f"{where}: {key} must be non-empty text.")
    return value


def _amount(item: dict, key: str, where: str, *, required=True):
    value = item.get(key)
    if value is None and not required:
        return decimal.Decimal(0)
    if not isinstance(value, str) or not _AMOUNT_RE.match(value):
        raise LedgerError(
            f"{where}: {key} must be a non-negative decimal string."
        )
    return decimal.Decimal(value)


def _date(item: dict, key: str, where: str) -> datetime.date:
    value = item.get(key)
    if not isinstance(value, str) or not _DATE_RE.match(value):
        raise LedgerError(f"{where}: {key} must be YYYY-MM-DD.")
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        raise LedgerError(f"{where}: {key} is not a date.") from None


def validate(ledger: dict) -> None:
    """Checks the whole ledger.

    Raises:
        LedgerError: Describing the first problem.
    """
    if not isinstance(ledger, dict) or ledger.get("schema_version") != (
        SCHEMA_VERSION
    ):
        raise LedgerError("Not an llm-metrics.cost-ledger.v1 file.")
    start = _date(ledger, "project_start", "ledger")
    cutoff = ledger.get("reporting_cutoff")
    if not isinstance(cutoff, str) or not _TIME_RE.match(cutoff):
        raise LedgerError("ledger: reporting_cutoff must be UTC time.")
    sources = ledger.get("sources")
    if not isinstance(sources, list) or not sources:
        raise LedgerError("ledger: sources must list every paid service.")
    ids = set()
    for source in sources:
        where = f"source {source.get('source_id')!r}"
        if not _ID_RE.match(str(source.get("source_id"))):
            raise LedgerError("source_id must be a lowercase id.")
        if source["source_id"] in ids:
            raise LedgerError(f"{where}: duplicate source.")
        ids.add(source["source_id"])
        _text(source, "vendor", where)
        _text(source, "service", where)
        if not isinstance(source.get("fully_reconciled"), bool):
            raise LedgerError(f"{where}: fully_reconciled must be true/false.")
        if source["fully_reconciled"]:
            _text(source, "reconciliation_method", where, limit=300)
            _date(source, "reconciled_through", where)
    entries = ledger.get("entries")
    if not isinstance(entries, list):
        raise LedgerError("ledger: entries must be a list (may be empty).")
    seen_ids, seen_evidence, charged_periods = set(), set(), {}
    for entry in entries:
        where = f"entry {entry.get('entry_id')!r}"
        if not _ID_RE.match(str(entry.get("entry_id"))):
            raise LedgerError("entry_id must be a lowercase id.")
        if entry["entry_id"] in seen_ids:
            raise LedgerError(f"{where}: duplicate entry id.")
        seen_ids.add(entry["entry_id"])
        if entry.get("source_id") not in ids:
            raise LedgerError(f"{where}: unknown source.")
        if entry.get("status") not in STATUSES:
            raise LedgerError(f"{where}: status must be one of {STATUSES}.")
        if not _CURRENCY_RE.match(str(entry.get("currency"))):
            raise LedgerError(f"{where}: currency must be ISO 4217.")
        period_start = _date(entry, "period_start", where)
        period_end = _date(entry, "period_end", where)
        if period_end < period_start or period_start < start:
            raise LedgerError(f"{where}: period is invalid or before start.")
        charged = _amount(entry, "charged_amount", where)
        for key in ("credits", "refunds", "taxes"):
            _amount(entry, key, where, required=False)
        if _amount(entry, "refunds", where, required=False) > charged:
            raise LedgerError(f"{where}: refunds exceed the charge.")
        _text(entry, "evidence_description", where, limit=300)
        evidence = entry.get("evidence_sha256")
        if not isinstance(evidence, str) or not _SHA_RE.match(evidence):
            raise LedgerError(f"{where}: evidence_sha256 must be SHA-256.")
        if evidence in seen_evidence:
            raise LedgerError(f"{where}: evidence already used (double count).")
        seen_evidence.add(evidence)
        verified = entry.get("last_verified_at")
        if not isinstance(verified, str) or not _TIME_RE.match(verified):
            raise LedgerError(f"{where}: last_verified_at must be UTC time.")
        private = entry.get("private_reference")
        if private is not None and not isinstance(private, str):
            raise LedgerError(f"{where}: private_reference must be text.")
        if entry["status"] == "charged":
            key = (entry["source_id"], entry["currency"])
            for other_start, other_end in charged_periods.get(key, []):
                if period_start <= other_end and other_start <= period_end:
                    raise LedgerError(
                        f"{where}: overlaps another charged period of the"
                        " same source (double count)."
                    )
            charged_periods.setdefault(key, []).append(
                (period_start, period_end)
            )


def load(path: pathlib.Path) -> Ledger:
    """Reads and validates a private ledger file."""
    path = pathlib.Path(path)
    if path.is_symlink() or not path.is_file():
        raise LedgerError("Ledger is not a regular file.")
    data = path.read_bytes()
    if len(data) > MAX_LEDGER_BYTES:
        raise LedgerError("Ledger is too large.")
    try:
        ledger = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise LedgerError("Ledger is not UTF-8 JSON.") from None
    validate(ledger)
    return Ledger(ledger, hashlib.sha256(data).hexdigest())


def _money(value: decimal.Decimal) -> str:
    return f"{value.quantize(decimal.Decimal('0.01'), decimal.ROUND_HALF_UP):,}"


def summarize(ledger: dict) -> dict:
    """Sanitized public summary (no private references).

    Returns per-currency verified charged subtotals, unpaid invoices,
    per-source coverage, and a lifetime total only when fully verified.
    """
    validate(ledger)
    by_source = {s["source_id"]: s for s in ledger["sources"]}
    charged, unpaid = {}, {}
    rows = []
    for source_id, source in by_source.items():
        entries = [e for e in ledger["entries"] if e["source_id"] == source_id]
        per_currency = {}
        for entry in entries:
            net = decimal.Decimal(entry["charged_amount"]) - decimal.Decimal(
                entry.get("refunds", "0")
            )
            if entry["status"] == "charged":
                per_currency[entry["currency"]] = (
                    per_currency.get(entry["currency"], decimal.Decimal(0))
                    + net
                )
                charged[entry["currency"]] = (
                    charged.get(entry["currency"], decimal.Decimal(0)) + net
                )
            elif entry["status"] == "invoiced_unpaid":
                unpaid[entry["currency"]] = (
                    unpaid.get(entry["currency"], decimal.Decimal(0)) + net
                )
        statuses = sorted({e["status"] for e in entries})
        reconciled = (
            source["fully_reconciled"]
            and source["reconciled_through"] >= ledger["reporting_cutoff"][:10]
            and statuses in (["charged"], [])
        )
        rows.append(
            {
                "vendor": source["vendor"],
                "service": source["service"],
                "charged": {
                    c: _money(v) for c, v in sorted(per_currency.items())
                },
                "status": (
                    "reconciled"
                    if reconciled
                    else "no billing records"
                    if not entries
                    else "not fully reconciled"
                ),
                "evidence": [
                    {
                        "description": e["evidence_description"],
                        "status": e["status"],
                        "period": f"{e['period_start']} to {e['period_end']}",
                        "sha256_prefix": e["evidence_sha256"][:12],
                    }
                    for e in sorted(entries, key=lambda e: e["period_start"])
                ],
                "last_verified_at": max(
                    (e["last_verified_at"] for e in entries), default=None
                ),
            }
        )
    complete = all(row["status"] == "reconciled" for row in rows) and not unpaid
    return {
        "schema_version": SUMMARY_SCHEMA,
        "project_start": ledger["project_start"],
        "reporting_cutoff": ledger["reporting_cutoff"],
        "verified_charged_subtotal": {
            c: _money(v) for c, v in sorted(charged.items())
        },
        "invoiced_unpaid": {c: _money(v) for c, v in sorted(unpaid.items())},
        "lifetime_total": (
            {c: _money(v) for c, v in sorted(charged.items())}
            if complete
            else None
        ),
        "lifetime_status": "verified" if complete else LIFETIME_UNVERIFIED,
        "unverified_sources": [
            f"{row['vendor']} {row['service']}"
            for row in rows
            if row["status"] != "reconciled"
        ],
        "sources": rows,
    }
