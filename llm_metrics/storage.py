"""Local SQLite storage for metric observations (standard-library sqlite3)."""

import sqlite3
from collections.abc import Iterable
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

# One row per observation. recorded_at is UTC ISO 8601 with a "Z" suffix,
# e.g. "2026-10-30T12:34:56.789012Z", so text order is time order.
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
    value_ms    REAL    NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS observations_unique
    ON observations (recorded_at, environment, provider, model, metric);
"""

# Constant SQL shared by both inserts; values are always bound as parameters.
_INSERT_TARGET = (
    "observations (recorded_at, environment, provider, model, metric, value_ms)"
    " VALUES (?, ?, ?, ?, ?, ?)"
)


def connect(db_path: Path) -> sqlite3.Connection:
    """Open the database, creating its directory and table if they are missing.

    Safe to call repeatedly: existing data is never changed. The caller closes
    the connection.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
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
        result["value_ms"],
    )


def save_observation(db_path: Path, result: dict, environment: str) -> None:
    """Append one measurement result (as returned by measure_ttft), timestamped now."""
    row = _row(datetime.now(timezone.utc), environment, result)
    with closing(connect(db_path)) as conn, conn:  # inner `conn` commits the insert
        conn.execute("INSERT INTO " + _INSERT_TARGET, row)


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
