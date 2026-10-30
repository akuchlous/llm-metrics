"""Local SQLite storage for benchmark requests and metric observations
(standard-library sqlite3)."""

import sqlite3
import uuid
from collections.abc import Iterable
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

# requests: one row per benchmark attempt (Step 010+), successful or not. `id`
# is llm-metrics' own identity for the attempt (a random UUID, hex), never a
# provider API request ID. `outcome` is "success" or a failure category (see
# outcomes.py). Prices are the effective USD rates per 1M tokens that apply to
# the attempt.
#   success: input_tokens/output_tokens (from the provider's Usage) and the
#            costs are known; failed_after_ms is NULL.
#   failure: token counts and costs are NULL, meaning UNKNOWN (never 0);
#            failed_after_ms is the time from request start until the failure
#            was detected (it is not total_latency).
# The table CHECK enforces exactly this.
# provider_request_id is the provider's own id for the attempt (OpenAI's
# x-request-id), kept beside our `id` for tracing with the provider; NULL when
# the provider gave none (simulated runs, connection failures, older rows).
# workload_id names the benchmark case that was run (e.g. "smoke.short_text.v1");
# origin_cloud / origin_region say where the benchmark runner executed (e.g.
# "local" / "unknown"), not where the provider served it. All three are
# required for new attempts and NULL (unknown) for rows recorded before Step 013.
#
# observations: one row per metric value. recorded_at is UTC ISO 8601 with a
# "Z" suffix, e.g. "2026-10-30T12:34:56.789012Z", so text order is time order.
# `value` is in the unit implied by `metric` (see latency.METRICS). request_id
# links a Step 010+ observation to its request; it is NULL for older and
# simulated-history rows, which have no request facts.
#
# Indexes that depend on columns added by upgrades are created in _upgrade().
_REQUESTS_TABLE = """
CREATE TABLE IF NOT EXISTS requests (
    id                          TEXT    PRIMARY KEY,
    recorded_at                 TEXT    NOT NULL,
    environment                 TEXT    NOT NULL CHECK (environment IN ('test', 'prod')),
    provider                    TEXT    NOT NULL,
    model                       TEXT    NOT NULL,
    outcome                     TEXT    NOT NULL CHECK (outcome IN (
        'success', 'timeout', 'rate_limited', 'provider_error',
        'transport_error', 'invalid_response')),
    input_tokens                INTEGER CHECK (input_tokens >= 0),
    requested_max_output_tokens INTEGER NOT NULL CHECK (requested_max_output_tokens >= 1),
    output_tokens               INTEGER CHECK (output_tokens >= 0),
    input_price_per_1m          REAL    NOT NULL CHECK (input_price_per_1m >= 0),
    output_price_per_1m         REAL    NOT NULL CHECK (output_price_per_1m >= 0),
    input_cost                  REAL,
    output_cost                 REAL,
    total_cost                  REAL,
    failed_after_ms             REAL    CHECK (failed_after_ms >= 0),
    provider_request_id         TEXT,
    workload_id                 TEXT,
    origin_cloud                TEXT,
    origin_region               TEXT,
    CHECK (
        (outcome = 'success'
            AND input_tokens IS NOT NULL AND output_tokens IS NOT NULL
            AND input_cost IS NOT NULL AND output_cost IS NOT NULL
            AND total_cost IS NOT NULL AND failed_after_ms IS NULL)
        OR
        (outcome <> 'success'
            AND input_tokens IS NULL AND output_tokens IS NULL
            AND input_cost IS NULL AND output_cost IS NULL
            AND total_cost IS NULL AND failed_after_ms IS NOT NULL)
    )
);
"""

SCHEMA = _REQUESTS_TABLE + """
CREATE TABLE IF NOT EXISTS observations (
    id          INTEGER PRIMARY KEY,
    recorded_at TEXT    NOT NULL,
    environment TEXT    NOT NULL CHECK (environment IN ('test', 'prod')),
    provider    TEXT    NOT NULL,
    model       TEXT    NOT NULL,
    metric      TEXT    NOT NULL,
    value       REAL    NOT NULL,
    request_id  TEXT    REFERENCES requests (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS observations_unique
    ON observations (recorded_at, environment, provider, model, metric);
"""

# Schema version stored in SQLite's `PRAGMA user_version`.
#   0: Steps 003-008 (value column named `value_ms`)
#   1: Step 009 (`value_ms` renamed to `value`; units depend on the metric)
#   2: Step 010 (`requests` table; observations.request_id)
#   3: Step 011 (requests.outcome, requests.failed_after_ms; token and cost
#      columns nullable for failed attempts)
#   4: Step 012a (requests.provider_request_id)
#   5: Step 013 (requests.workload_id, origin_cloud, origin_region)
SCHEMA_VERSION = 5

# Constant SQL; values are always bound as parameters.
_INSERT_OBSERVATION = (
    "observations (recorded_at, environment, provider, model, metric, value, request_id)"
    " VALUES (?, ?, ?, ?, ?, ?, ?)"
)
_REQUEST_COLUMNS = (
    "id", "recorded_at", "environment", "provider", "model", "outcome",
    "input_tokens", "requested_max_output_tokens", "output_tokens",
    "input_price_per_1m", "output_price_per_1m",
    "input_cost", "output_cost", "total_cost", "failed_after_ms", "provider_request_id",
    "workload_id", "origin_cloud", "origin_region",
)
# Request facts every new attempt must supply (NULL only in older rows).
_REQUIRED_NEW_FACTS = ("workload_id", "origin_cloud", "origin_region")
# Columns of a version-2 requests table, copied as-is by the version 3 upgrade.
_V2_REQUEST_COLUMNS = (
    "id", "recorded_at", "environment", "provider", "model",
    "input_tokens", "requested_max_output_tokens", "output_tokens",
    "input_price_per_1m", "output_price_per_1m", "input_cost", "output_cost", "total_cost",
)


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _upgrade(conn: sqlite3.Connection) -> None:
    """Bring an existing database up to SCHEMA_VERSION. Existing rows are kept.

    All steps and the version bump run in one IMMEDIATE transaction, so an
    upgrade is all-or-nothing and concurrent first connections serialize.
    """
    if conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION:
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]  # re-read under lock
        if version > SCHEMA_VERSION:
            raise RuntimeError(
                f"Database schema version {version} is newer than this code supports "
                f"({SCHEMA_VERSION}). Update llm-metrics."
            )
        if version < 1 and "value_ms" in _columns(conn, "observations"):
            conn.execute("ALTER TABLE observations RENAME COLUMN value_ms TO value")
        if version < 2:
            if "request_id" not in _columns(conn, "observations"):
                conn.execute(
                    "ALTER TABLE observations ADD COLUMN request_id TEXT REFERENCES requests (id)"
                )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS observations_request ON observations (request_id)"
            )
        if version < 3 and "outcome" not in _columns(conn, "requests"):
            # SQLite cannot drop NOT NULL, so rebuild the table from the current
            # definition. Every Step 010 request row was a completed, successful
            # request: copy it with outcome 'success' and failed_after_ms NULL.
            conn.execute(_REQUESTS_TABLE.replace("IF NOT EXISTS requests", "requests_v3"))
            columns = ", ".join(_V2_REQUEST_COLUMNS)
            conn.execute(
                f"INSERT INTO requests_v3 ({columns}, outcome, failed_after_ms)"
                f" SELECT {columns}, 'success', NULL FROM requests"
            )
            conn.execute("DROP TABLE requests")
            conn.execute("ALTER TABLE requests_v3 RENAME TO requests")
        if version < 4 and "provider_request_id" not in _columns(conn, "requests"):
            # Existing attempts keep NULL: their provider ids were never recorded.
            conn.execute("ALTER TABLE requests ADD COLUMN provider_request_id TEXT")
        if version < 5:
            # Workload and origin were never recorded for existing attempts, and
            # the workload was not stable (the first real attempt was sent
            # without reasoning.effort), so they stay NULL rather than guessed.
            existing = _columns(conn, "requests")
            for column in _REQUIRED_NEW_FACTS:
                if column not in existing:
                    conn.execute(f"ALTER TABLE requests ADD COLUMN {column} TEXT")
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


def connect(db_path: Path) -> sqlite3.Connection:
    """Open the database, creating its directory and tables if they are missing
    and upgrading an older schema in place.

    Safe to call repeatedly: existing rows are never changed or lost. The caller
    closes the connection.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        _upgrade(conn)
    except BaseException:
        conn.close()
        raise
    return conn


def format_timestamp(moment: datetime) -> str:
    """UTC datetime -> stored recorded_at text."""
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _observation_row(
    recorded_at: str, environment: str, result: dict, request_id: str | None
) -> tuple:
    return (
        recorded_at,
        environment,
        result["provider"],
        result["model"],
        result["metric"],
        result["value"],
        request_id,
    )


def save_request(db_path: Path, request: dict, results: list[dict], environment: str) -> str:
    """Save one benchmark attempt and its metric observations; return its new id.

    `request` must hold every _REQUEST_COLUMNS key except id, recorded_at and
    environment (unknown facts of a failed attempt as None); provider_request_id
    is optional (None when absent). workload_id, origin_cloud and origin_region
    must be non-empty strings. A failed attempt has
    no observations. The request row and all observations share one timestamp and
    are written in one transaction: either everything is saved or nothing.
    """
    if request["outcome"] != "success" and results:
        raise ValueError("A failed attempt must not have metric observations.")
    for fact in _REQUIRED_NEW_FACTS:
        if not isinstance(request.get(fact), str) or not request[fact]:
            raise ValueError(f"A new attempt must have a non-empty {fact}.")
    request_id = uuid.uuid4().hex
    recorded_at = format_timestamp(datetime.now(timezone.utc))
    row = {"provider_request_id": None, **request, "id": request_id, "recorded_at": recorded_at, "environment": environment}
    values = tuple(row[column] for column in _REQUEST_COLUMNS)
    observations = [_observation_row(recorded_at, environment, r, request_id) for r in results]
    with closing(connect(db_path)) as conn, conn:  # inner `conn` commits
        conn.execute(
            f"INSERT INTO requests ({', '.join(_REQUEST_COLUMNS)})"
            f" VALUES ({', '.join('?' for _ in _REQUEST_COLUMNS)})",
            values,
        )
        conn.executemany("INSERT INTO " + _INSERT_OBSERVATION, observations)
    return request_id


def save_new_observations(
    db_path: Path, observations: Iterable[tuple[datetime, dict]], environment: str
) -> int:
    """Insert (recorded_at, result) pairs with explicit timestamps in one transaction.

    These observations have no request (request_id NULL). An observation that
    already exists (same recorded_at, environment, provider, model and metric)
    is skipped. Returns the number of rows inserted.
    """
    rows = [
        _observation_row(format_timestamp(recorded_at), environment, result, None)
        for recorded_at, result in observations
    ]
    with closing(connect(db_path)) as conn, conn:
        cursor = conn.executemany("INSERT OR IGNORE INTO " + _INSERT_OBSERVATION, rows)
        return cursor.rowcount


def load_observations(
    db_path: Path,
    environment: str,
    provider: str,
    model: str,
    metric: str,
    *,
    start: datetime,
    end: datetime,
) -> list[tuple[str, float]]:
    """Return (recorded_at, value) for matching observations, oldest first.

    Only observations with start <= recorded_at <= end (both inclusive) are
    returned. recorded_at is fixed-width UTC text, so text comparison is time
    comparison.
    """
    with closing(connect(db_path)) as conn:
        return conn.execute(
            "SELECT recorded_at, value FROM observations"
            " WHERE environment = ? AND provider = ? AND model = ? AND metric = ?"
            " AND recorded_at >= ? AND recorded_at <= ?"
            " ORDER BY recorded_at, id",
            (
                environment,
                provider,
                model,
                metric,
                format_timestamp(start),
                format_timestamp(end),
            ),
        ).fetchall()


def _request_dicts(conn: sqlite3.Connection, where: str, params: tuple) -> list[dict]:
    """Requests matching `where` (constant SQL), newest first, each with a
    "metrics" dict {metric: value} of its linked observations."""
    columns = ", ".join(f"r.{c}" for c in _REQUEST_COLUMNS)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        f"SELECT {columns}, o.metric, o.value FROM requests r"
        " LEFT JOIN observations o ON o.request_id = r.id"
        f" WHERE {where} ORDER BY r.recorded_at DESC, r.id, o.id",
        params,
    ).fetchall()
    requests: dict[str, dict] = {}
    for row in rows:
        request = requests.setdefault(
            row["id"], {**{c: row[c] for c in _REQUEST_COLUMNS}, "metrics": {}}
        )
        if row["metric"] is not None:
            request["metrics"][row["metric"]] = row["value"]
    return list(requests.values())


def load_request(db_path: Path, request_id: str) -> dict | None:
    """One request's facts plus its metrics, or None if there is no such request."""
    with closing(connect(db_path)) as conn:
        found = _request_dicts(conn, "r.id = ?", (request_id,))
    return found[0] if found else None


def load_recent_requests(db_path: Path, environment: str, limit: int) -> list[dict]:
    """The `limit` most recent requests in `environment`, newest first, with metrics."""
    with closing(connect(db_path)) as conn:
        return _request_dicts(
            conn,
            "r.id IN (SELECT id FROM requests WHERE environment = ?"
            " ORDER BY recorded_at DESC, id LIMIT ?)",
            (environment, limit),
        )


def count_outcomes(
    db_path: Path,
    environment: str,
    provider: str,
    model: str,
    *,
    start: datetime,
    end: datetime,
) -> dict[str, int]:
    """{outcome: attempts} for attempts with start <= recorded_at <= end (inclusive).

    The population is the `requests` table only: every persisted benchmark
    attempt. Observations without a request (before Step 010, simulated history)
    are not attempts and are not counted.
    """
    with closing(connect(db_path)) as conn:
        return dict(conn.execute(
            "SELECT outcome, COUNT(*) FROM requests"
            " WHERE environment = ? AND provider = ? AND model = ?"
            " AND recorded_at >= ? AND recorded_at <= ?"
            " GROUP BY outcome",
            (environment, provider, model, format_timestamp(start), format_timestamp(end)),
        ).fetchall())


def spend_by_model(
    db_path: Path, environment: str, *, start: datetime, end: datetime
) -> list[dict]:
    """Benchmark API spend per provider/model for attempts with
    start <= recorded_at <= end (inclusive), most expensive first.

    Each row: provider, model, attempts, successful_calls, failed_attempts,
    input_tokens, output_tokens, total_cost. Tokens and cost are summed over
    successful attempts only (their known, stored values); failed attempts have
    unknown cost and are only counted, never added as $0. total_cost is None
    when the group has no successful attempt. Computed at query time from the
    request rows, which stay the source of truth.
    """
    with closing(connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT provider, model, COUNT(*) AS attempts,"
            " SUM(outcome = 'success') AS successful_calls,"
            " SUM(outcome <> 'success') AS failed_attempts,"
            " SUM(CASE WHEN outcome = 'success' THEN input_tokens END) AS input_tokens,"
            " SUM(CASE WHEN outcome = 'success' THEN output_tokens END) AS output_tokens,"
            " SUM(CASE WHEN outcome = 'success' THEN total_cost END) AS total_cost"
            " FROM requests"
            " WHERE environment = ? AND recorded_at >= ? AND recorded_at <= ?"
            " GROUP BY provider, model"
            " ORDER BY total_cost IS NULL, total_cost DESC, provider, model",
            (environment, format_timestamp(start), format_timestamp(end)),
        ).fetchall()
    return [dict(row) for row in rows]
