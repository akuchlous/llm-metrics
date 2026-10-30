"""Local SQLite storage for metric observations (standard-library sqlite3)."""

import sqlite3
from collections.abc import Iterable
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

# One row per observation. recorded_at is UTC ISO 8601 with a "Z" suffix,
# e.g. "2026-10-30T12:34:56.789012Z", so text order is time order. `value` is in
# the unit implied by `metric` (see llm_metrics.latency.METRICS).
# The unique index makes re-inserting the same observation detectable; it is a
# separate statement so it is also added to databases created before it existed.
SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    id          INTEGER PRIMARY KEY,
    recorded_at TEXT    NOT NULL,
    environment TEXT    NOT NULL CHECK (environment IN ('test', 'prod')),
    provider    TEXT    NOT NULL,
    model       TEXT    NOT NULL,
    metric      TEXT    NOT NULL,
    value       REAL    NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS observations_unique
    ON observations (recorded_at, environment, provider, model, metric);
"""

# Constant SQL shared by both inserts; values are always bound as parameters.
_INSERT_TARGET = (
    "observations (recorded_at, environment, provider, model, metric, value)"
    " VALUES (?, ?, ?, ?, ?, ?)"
)


# Schema version stored in SQLite's `PRAGMA user_version`.
#   0: Steps 003-008 (value column named `value_ms`)
#   1: Step 009 (`value_ms` renamed to `value`; units depend on the metric)
SCHEMA_VERSION = 1


def _upgrade(conn: sqlite3.Connection) -> None:
    """Bring an existing database up to SCHEMA_VERSION. Existing rows are kept."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema version {version} is newer than this code supports "
            f"({SCHEMA_VERSION}). Update llm-metrics."
        )
    if version < 1:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(observations)")}
        if "value_ms" in columns:
            conn.execute("ALTER TABLE observations RENAME COLUMN value_ms TO value")
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def connect(db_path: Path) -> sqlite3.Connection:
    """Open the database, creating its directory and table if they are missing
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


def _row(recorded_at: datetime, environment: str, result: dict) -> tuple:
    return (
        format_timestamp(recorded_at),
        environment,
        result["provider"],
        result["model"],
        result["metric"],
        result["value"],
    )


def save_observations(db_path: Path, results: list[dict], environment: str) -> None:
    """Append measurement results from one request, all timestamped now.

    The rows are written in one transaction: either all are saved or none.
    """
    recorded_at = datetime.now(timezone.utc)
    rows = [_row(recorded_at, environment, result) for result in results]
    with closing(connect(db_path)) as conn, conn:  # inner `conn` commits the inserts
        conn.executemany("INSERT INTO " + _INSERT_TARGET, rows)


def save_new_observations(
    db_path: Path, observations: Iterable[tuple[datetime, dict]], environment: str
) -> int:
    """Insert (recorded_at, result) pairs with explicit timestamps in one transaction.

    An observation that already exists (same recorded_at, environment, provider,
    model and metric) is skipped. Returns the number of rows inserted.
    """
    rows = [_row(recorded_at, environment, result) for recorded_at, result in observations]
    with closing(connect(db_path)) as conn, conn:
        cursor = conn.executemany("INSERT OR IGNORE INTO " + _INSERT_TARGET, rows)
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
