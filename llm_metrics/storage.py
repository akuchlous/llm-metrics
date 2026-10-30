"""Local SQLite storage for metric observations (standard-library sqlite3)."""

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

# One row per successful measurement. recorded_at is UTC ISO 8601 with a "Z"
# suffix, e.g. "2026-10-30T12:34:56.789012Z", so text order is time order.
SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    id          INTEGER PRIMARY KEY,
    recorded_at TEXT    NOT NULL,
    environment TEXT    NOT NULL CHECK (environment IN ('test', 'prod')),
    provider    TEXT    NOT NULL,
    model       TEXT    NOT NULL,
    metric      TEXT    NOT NULL,
    value_ms    REAL    NOT NULL
)
"""


def connect(db_path: Path) -> sqlite3.Connection:
    """Open the database, creating its directory and table if they are missing.

    Safe to call repeatedly: existing data is never changed. The caller closes
    the connection.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(SCHEMA)
    return conn


def save_observation(db_path: Path, result: dict, environment: str) -> None:
    """Append one measurement result (as returned by measure_ttft) to the database."""
    recorded_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    with closing(connect(db_path)) as conn, conn:  # inner `conn` commits the insert
        conn.execute(
            "INSERT INTO observations"
            " (recorded_at, environment, provider, model, metric, value_ms)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                recorded_at,
                environment,
                result["provider"],
                result["model"],
                result["metric"],
                result["value_ms"],
            ),
        )
