"""Local SQLite storage for benchmark attempts and metric observations.

Owns the schema, in-place upgrades of older databases, and every read and
write of benchmark data. It knows nothing about providers, HTTP, or HTML.
All SQL is constant text; values are always bound as parameters.

Tables:

requests: one row per benchmark attempt, successful or not.
    - `id` is llm-metrics' own identity for the attempt (random UUID, hex),
      never a provider id.
    - `outcome` is "success" or a failure category (see `outcomes`).
    - Prices are the effective USD rates per 1M tokens used for the cost.
    - On success, token counts (from the provider's `Usage`) and costs are
      known and `failed_after_ms` is NULL. On failure, token counts and costs
      are NULL, meaning UNKNOWN (never 0), and `failed_after_ms` is the time
      until the failure was detected (not a latency). A table CHECK enforces
      exactly this.
    - `provider_request_id` is the provider's own id (OpenAI `x-request-id`),
      kept beside `id` for tracing with the provider; NULL when none was given.
    - `workload_id` names the benchmark case that was run. `origin_cloud` /
      `origin_region` say where the benchmark runner executed, not where the
      provider served the request. `cache_policy` is what the request asked of
      the provider's prompt cache (see `providers.CACHE_POLICIES`). All four
      are required for new attempts; older rows have NULL workload/origin and
      cache policy "unknown".
    - `cached_input_tokens` is the provider-reported cached part of
      `input_tokens`: 0 means the provider reported zero, NULL means not
      reported or unknown.

observations: one row per metric value.
    - `recorded_at` is UTC ISO 8601 text with a "Z" suffix and fixed width,
      e.g. "2026-10-30T12:34:56.789012Z", so text order is time order.
    - `value` is in the unit implied by `metric` (see `latency.METRICS`).
    - `request_id` links an observation to its attempt; NULL for simulated
      history and observations recorded before attempts were stored, which
      have no attempt facts and are not attempts.
"""

from collections.abc import Iterable
import contextlib
import datetime
import pathlib
import sqlite3
import uuid

# The current requests table. Also used by the version 3 upgrade to rebuild an
# older table, which is why upgrades add later columns only if missing.
_REQUESTS_TABLE = """
CREATE TABLE IF NOT EXISTS requests (
    id                          TEXT    PRIMARY KEY,
    recorded_at                 TEXT    NOT NULL,
    environment                 TEXT    NOT NULL
                                        CHECK (environment IN ('test', 'prod')),
    provider                    TEXT    NOT NULL,
    model                       TEXT    NOT NULL,
    outcome                     TEXT    NOT NULL CHECK (outcome IN (
        'success', 'timeout', 'rate_limited', 'provider_error',
        'transport_error', 'invalid_response')),
    input_tokens                INTEGER CHECK (input_tokens >= 0),
    requested_max_output_tokens INTEGER NOT NULL
                                CHECK (requested_max_output_tokens >= 1),
    output_tokens               INTEGER CHECK (output_tokens >= 0),
    input_price_per_1m          REAL    NOT NULL
                                        CHECK (input_price_per_1m >= 0),
    output_price_per_1m         REAL    NOT NULL
                                        CHECK (output_price_per_1m >= 0),
    input_cost                  REAL,
    output_cost                 REAL,
    total_cost                  REAL,
    failed_after_ms             REAL    CHECK (failed_after_ms >= 0),
    provider_request_id         TEXT,
    workload_id                 TEXT,
    origin_cloud                TEXT,
    origin_region               TEXT,
    cache_policy                TEXT    CHECK (cache_policy IN (
        'disabled', 'enabled', 'provider_default', 'unknown')),
    cached_input_tokens         INTEGER CHECK (cached_input_tokens >= 0),
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

# Schema version stored in SQLite's `PRAGMA user_version`, and what each
# version added. `_upgrade` applies every later step in order.
#   0: Steps 003-008: observations with a `value_ms` column.
#   1: Step 009: `value_ms` renamed to `value` (units depend on the metric).
#   2: Step 010: `requests` table; observations.request_id.
#   3: Step 011: requests.outcome and failed_after_ms; token and cost columns
#      nullable for failed attempts.
#   4: Step 012a: requests.provider_request_id.
#   5: Step 013: requests.workload_id, origin_cloud, origin_region.
#   6: Step 013: requests.cache_policy and cached_input_tokens.
SCHEMA_VERSION = 6

_INSERT_OBSERVATION = (
    "observations (recorded_at, environment, provider, model, metric, value,"
    " request_id) VALUES (?, ?, ?, ?, ?, ?, ?)"
)
_REQUEST_COLUMNS = (
    "id",
    "recorded_at",
    "environment",
    "provider",
    "model",
    "outcome",
    "input_tokens",
    "requested_max_output_tokens",
    "output_tokens",
    "input_price_per_1m",
    "output_price_per_1m",
    "input_cost",
    "output_cost",
    "total_cost",
    "failed_after_ms",
    "provider_request_id",
    "workload_id",
    "origin_cloud",
    "origin_region",
    "cache_policy",
    "cached_input_tokens",
)
# Conditions every new attempt must record. The columns stay nullable only so
# older rows can honestly say "unknown"; `save_request` enforces them.
_REQUIRED_NEW_FACTS = (
    "workload_id",
    "origin_cloud",
    "origin_region",
    "cache_policy",
)
# Columns of a version-2 requests table, copied as-is by the version 3 upgrade.
_V2_REQUEST_COLUMNS = (
    "id",
    "recorded_at",
    "environment",
    "provider",
    "model",
    "input_tokens",
    "requested_max_output_tokens",
    "output_tokens",
    "input_price_per_1m",
    "output_price_per_1m",
    "input_cost",
    "output_cost",
    "total_cost",
)


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _upgrade(conn: sqlite3.Connection) -> None:
    """Brings an existing database up to `SCHEMA_VERSION`, keeping every row.

    All steps and the version bump run in one IMMEDIATE transaction, so an
    upgrade is all-or-nothing and concurrent first connections serialize.
    Facts that were never recorded for older rows stay unknown (NULL or
    "unknown"); nothing is backfilled or guessed.

    Raises:
        RuntimeError: If the database is newer than this code.
    """
    if conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION:
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        # Re-read under the lock: another connection may have upgraded.
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError(
                f"Database schema version {version} is newer than this code"
                f" supports ({SCHEMA_VERSION}). Update llm-metrics."
            )
        if version < 1 and "value_ms" in _columns(conn, "observations"):
            conn.execute(
                "ALTER TABLE observations RENAME COLUMN value_ms TO value"
            )
        if version < 2:
            if "request_id" not in _columns(conn, "observations"):
                conn.execute(
                    "ALTER TABLE observations ADD COLUMN request_id TEXT"
                    " REFERENCES requests (id)"
                )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS observations_request"
                " ON observations (request_id)"
            )
        if version < 3 and "outcome" not in _columns(conn, "requests"):
            # SQLite cannot drop NOT NULL, so rebuild the table from the
            # current definition. Version 2 stored only completed, successful
            # requests, so each row is copied with outcome 'success'.
            conn.execute(
                _REQUESTS_TABLE.replace("IF NOT EXISTS requests", "requests_v3")
            )
            columns = ", ".join(_V2_REQUEST_COLUMNS)
            conn.execute(
                f"INSERT INTO requests_v3 ({columns}, outcome, failed_after_ms)"
                f" SELECT {columns}, 'success', NULL FROM requests"
            )
            conn.execute("DROP TABLE requests")
            conn.execute("ALTER TABLE requests_v3 RENAME TO requests")
        if version < 4 and "provider_request_id" not in _columns(
            conn, "requests"
        ):
            conn.execute(
                "ALTER TABLE requests ADD COLUMN provider_request_id TEXT"
            )
        if version < 5:
            # Workload and origin stay NULL for older rows: they were never
            # recorded, and the real workload was not stable over that period,
            # so any label would be a guess.
            existing = _columns(conn, "requests")
            for column in ("workload_id", "origin_cloud", "origin_region"):
                if column not in existing:
                    conn.execute(
                        f"ALTER TABLE requests ADD COLUMN {column} TEXT"
                    )
        if version < 6:
            if "cache_policy" not in _columns(conn, "requests"):
                conn.execute(
                    "ALTER TABLE requests ADD COLUMN cache_policy TEXT"
                    " CHECK (cache_policy IN ("
                    "'disabled', 'enabled', 'provider_default', 'unknown'))"
                )
                conn.execute(
                    "ALTER TABLE requests ADD COLUMN cached_input_tokens"
                    " INTEGER CHECK (cached_input_tokens >= 0)"
                )
            # Older attempts' policy cannot be established: "unknown" exists
            # for exactly this. Cached tokens stay NULL, never 0. This also
            # covers tables rebuilt above, which already have the columns.
            conn.execute(
                "UPDATE requests SET cache_policy = 'unknown'"
                " WHERE cache_policy IS NULL"
            )
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


def connect(db_path: pathlib.Path) -> sqlite3.Connection:
    """Opens the database, creating and upgrading it as needed.

    Creates the parent directory and missing tables, and upgrades an older
    schema in place. Safe to call repeatedly: existing rows are never changed
    or lost.

    Returns:
        An open connection; the caller closes it.

    Raises:
        RuntimeError: If the database is newer than this code.
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


def format_timestamp(moment: datetime.datetime) -> str:
    """Formats an aware datetime as stored `recorded_at` text (UTC)."""
    return moment.astimezone(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )


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


def save_request(
    db_path: pathlib.Path, request: dict, results: list[dict], environment: str
) -> str:
    """Saves one benchmark attempt and its metric observations atomically.

    The request row and all observations share one timestamp and are written
    in one transaction: either everything is saved or nothing.

    Args:
        db_path: Database file.
        request: Every `_REQUEST_COLUMNS` key except "id", "recorded_at", and
            "environment", with unknown facts of a failed attempt as None.
            "provider_request_id" and "cached_input_tokens" may be omitted
            (stored as NULL). Extra keys (e.g. "diagnostics") are ignored.
        results: Metric observations; must be empty for a failed attempt.
        environment: "test" or "prod".

    Returns:
        The new request's id.

    Raises:
        ValueError: If a failed attempt has observations, or a required
            condition (workload, origin, cache policy) is missing or empty.
            Nothing is written.
        sqlite3.IntegrityError: If facts violate the table's CHECKs.
    """
    if request["outcome"] != "success" and results:
        raise ValueError("A failed attempt must not have metric observations.")
    for fact in _REQUIRED_NEW_FACTS:
        if not isinstance(request.get(fact), str) or not request[fact]:
            raise ValueError(f"A new attempt must have a non-empty {fact}.")
    request_id = uuid.uuid4().hex
    recorded_at = format_timestamp(datetime.datetime.now(datetime.timezone.utc))
    row = {
        "provider_request_id": None,
        "cached_input_tokens": None,
        **request,
        "id": request_id,
        "recorded_at": recorded_at,
        "environment": environment,
    }
    values = tuple(row[column] for column in _REQUEST_COLUMNS)
    observations = [
        _observation_row(recorded_at, environment, result, request_id)
        for result in results
    ]
    with contextlib.closing(connect(db_path)) as conn:
        # The connection context manager commits on success and rolls back
        # on any exception, making the two inserts one transaction.
        with conn:
            conn.execute(
                f"INSERT INTO requests ({', '.join(_REQUEST_COLUMNS)})"
                f" VALUES ({', '.join('?' for _ in _REQUEST_COLUMNS)})",
                values,
            )
            conn.executemany("INSERT INTO " + _INSERT_OBSERVATION, observations)
    return request_id


def save_new_observations(
    db_path: pathlib.Path,
    observations: Iterable[tuple[datetime.datetime, dict]],
    environment: str,
) -> int:
    """Inserts observations that belong to no attempt, skipping duplicates.

    Used for simulated history. An observation that already exists (same
    recorded_at, environment, provider, model, and metric) is skipped, which
    makes seeding idempotent. All rows are written in one transaction.

    Args:
        db_path: Database file.
        observations: (recorded_at, observation) pairs with explicit times.
        environment: "test" or "prod".

    Returns:
        The number of rows inserted.
    """
    rows = [
        _observation_row(
            format_timestamp(recorded_at), environment, result, None
        )
        for recorded_at, result in observations
    ]
    with contextlib.closing(connect(db_path)) as conn:
        with conn:
            cursor = conn.executemany(
                "INSERT OR IGNORE INTO " + _INSERT_OBSERVATION, rows
            )
            return cursor.rowcount


def load_observations(
    db_path: pathlib.Path,
    environment: str,
    provider: str,
    model: str,
    metric: str,
    *,
    start: datetime.datetime,
    end: datetime.datetime,
    cache_policy: str | None = None,
) -> list[tuple[str, float]]:
    """Loads one metric's observations in a time window, oldest first.

    Args:
        db_path: Database file.
        environment: "test" or "prod".
        provider: Provider name.
        model: Model name.
        metric: A key of `latency.METRICS`.
        start: Inclusive window start (aware datetime).
        end: Inclusive window end (aware datetime).
        cache_policy: If given, only observations of attempts with this policy
            are returned (observations without an attempt have no policy and
            are excluded), so different cache populations are never mixed.

    Returns:
        (recorded_at, value) pairs. Window bounds compare as text, which is
        correct because `recorded_at` is fixed-width UTC text.
    """
    params = [
        environment,
        provider,
        model,
        metric,
        format_timestamp(start),
        format_timestamp(end),
    ]
    sql = (
        "SELECT o.recorded_at, o.value FROM observations o"
        " WHERE o.environment = ? AND o.provider = ? AND o.model = ?"
        " AND o.metric = ? AND o.recorded_at >= ? AND o.recorded_at <= ?"
    )
    if cache_policy is not None:
        sql += (
            " AND o.request_id IN"
            " (SELECT id FROM requests WHERE cache_policy = ?)"
        )
        params.append(cache_policy)
    with contextlib.closing(connect(db_path)) as conn:
        return conn.execute(
            sql + " ORDER BY o.recorded_at, o.id", params
        ).fetchall()


def _request_dicts(
    conn: sqlite3.Connection, where: str, params: tuple
) -> list[dict]:
    """Loads requests matching `where`, newest first, with their metrics.

    Args:
        conn: Open connection.
        where: Constant SQL condition on alias `r` (requests); never built
            from user input.
        params: Values bound to the placeholders in `where`.

    Returns:
        One dict per request with every `_REQUEST_COLUMNS` key plus "metrics"
        ({metric: value} of its linked observations; empty for failures).
    """
    columns = ", ".join(f"r.{column}" for column in _REQUEST_COLUMNS)
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
            row["id"],
            {
                **{column: row[column] for column in _REQUEST_COLUMNS},
                "metrics": {},
            },
        )
        if row["metric"] is not None:
            request["metrics"][row["metric"]] = row["value"]
    return list(requests.values())


def load_request(db_path: pathlib.Path, request_id: str) -> dict | None:
    """Returns one request with its metrics (see `_request_dicts`), or None."""
    with contextlib.closing(connect(db_path)) as conn:
        found = _request_dicts(conn, "r.id = ?", (request_id,))
    return found[0] if found else None


def load_recent_requests(
    db_path: pathlib.Path, environment: str, limit: int
) -> list[dict]:
    """Returns the `limit` most recent requests in `environment`, newest first.

    Each request includes its metrics; see `_request_dicts`.
    """
    with contextlib.closing(connect(db_path)) as conn:
        return _request_dicts(
            conn,
            "r.id IN (SELECT id FROM requests WHERE environment = ?"
            " ORDER BY recorded_at DESC, id LIMIT ?)",
            (environment, limit),
        )


def count_outcomes(
    db_path: pathlib.Path,
    environment: str,
    provider: str,
    model: str,
    *,
    start: datetime.datetime,
    end: datetime.datetime,
) -> dict[str, int]:
    """Counts attempts per outcome in an inclusive time window.

    The population is the requests table only: every persisted attempt.
    Observations without an attempt (simulated history, early data) are not
    attempts and are not counted.

    Returns:
        {outcome: attempts}; outcomes with no attempts are absent.
    """
    with contextlib.closing(connect(db_path)) as conn:
        return dict(
            conn.execute(
                "SELECT outcome, COUNT(*) FROM requests"
                " WHERE environment = ? AND provider = ? AND model = ?"
                " AND recorded_at >= ? AND recorded_at <= ?"
                " GROUP BY outcome",
                (
                    environment,
                    provider,
                    model,
                    format_timestamp(start),
                    format_timestamp(end),
                ),
            ).fetchall()
        )


def spend_by_model(
    db_path: pathlib.Path,
    environment: str,
    *,
    start: datetime.datetime,
    end: datetime.datetime,
) -> list[dict]:
    """Sums benchmark API spend per provider/model in an inclusive window.

    Computed at query time from the request rows, which stay the source of
    truth. Tokens and cost are summed over successful attempts only (their
    known, stored values). Failed attempts have unknown cost: they are counted
    but never added as $0.

    Returns:
        One dict per provider/model, most expensive first, with "provider",
        "model", "attempts", "successful_calls", "failed_attempts",
        "input_tokens", "output_tokens", and "total_cost". "total_cost" is None
        when the group has no successful attempt.
    """
    with contextlib.closing(connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT provider, model, COUNT(*) AS attempts,"
            " SUM(outcome = 'success') AS successful_calls,"
            " SUM(outcome <> 'success') AS failed_attempts,"
            " SUM(CASE WHEN outcome = 'success' THEN input_tokens END)"
            " AS input_tokens,"
            " SUM(CASE WHEN outcome = 'success' THEN output_tokens END)"
            " AS output_tokens,"
            " SUM(CASE WHEN outcome = 'success' THEN total_cost END)"
            " AS total_cost"
            " FROM requests"
            " WHERE environment = ? AND recorded_at >= ? AND recorded_at <= ?"
            " GROUP BY provider, model"
            " ORDER BY total_cost IS NULL, total_cost DESC, provider, model",
            (environment, format_timestamp(start), format_timestamp(end)),
        ).fetchall()
    return [dict(row) for row in rows]
