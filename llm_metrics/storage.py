"""SQLAlchemy Core storage for benchmark attempts and metric observations.

Owns the schema, Alembic-managed migrations, and every read and write of
benchmark data. It knows nothing about providers, HTTP, or HTML.
All SQL uses SQLAlchemy Core constructs; values are always bound as
parameters.

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
    - `request_profile_id` names the provider request settings the attempt
      was made under (see `targets`); required for new attempts, NULL
      (unknown) for older rows. `cached_input_price_per_1m` is the cached
      input rate of the cost basis, NULL when none is defined (older rows,
      the simulated provider).

observations: one row per metric value.
    - `recorded_at` is UTC ISO 8601 text with a "Z" suffix and fixed width,
      e.g. "2026-10-30T12:34:56.789012Z", so text order is time order.
    - `value` is in the unit implied by `metric` (see `latency.METRICS`).
    - `request_id` links an observation to its attempt; NULL for simulated
      history and observations recorded before attempts were stored, which
      have no attempt facts and are not attempts.

Migration strategy:
    - Fresh databases: Alembic creates all tables via `upgrade head`.
    - Pre-Alembic databases (schema v0–v7): the legacy upgrade bridge brings
      them to v7, then Alembic stamps the head revision without re-running DDL.
    - Alembic-managed databases: `upgrade head` applies any pending revisions.
"""

from collections.abc import Iterable
import datetime
import pathlib
import uuid

from sqlalchemy import (
    CheckConstraint,
    Column,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    Table,
    Text,
    case,
    create_engine,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import insert as _pg_insert
from sqlalchemy.dialects.sqlite import insert as _sqlite_insert
from sqlalchemy.engine import Connection, Engine
import sqlalchemy.exc

# The current requests table as a SQL string. Kept for:
#   1. The legacy v0→v7 upgrade bridge (_legacy_upgrade) which uses it to
#      rebuild the table during the v3 upgrade step.
#   2. The test that constructs a v6 database by removing the last two columns
#      from this string (test_version_6_rows_keep_an_unknown_request_profile).
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
    request_profile_id          TEXT,
    cached_input_price_per_1m   REAL    CHECK (cached_input_price_per_1m >= 0),
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

# Schema version stored in SQLite's `PRAGMA user_version` for the legacy
# upgrade bridge. Alembic takes over from v7 onward.
#   0: Steps 003-008: observations with a `value_ms` column.
#   1: Step 009: `value_ms` renamed to `value`.
#   2: Step 010: `requests` table; observations.request_id.
#   3: Step 011: requests.outcome and failed_after_ms; nullable token/cost.
#   4: Step 012a: requests.provider_request_id.
#   5: Step 013: requests.workload_id, origin_cloud, origin_region.
#   6: Step 013: requests.cache_policy and cached_input_tokens.
#   7: Step 016: requests.request_profile_id and cached_input_price_per_1m.
SCHEMA_VERSION = 7

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
    "request_profile_id",
    "cached_input_price_per_1m",
)
# Conditions every new attempt must record. The columns stay nullable only so
# older rows can honestly say "unknown"; `save_request` enforces them.
_REQUIRED_NEW_FACTS = (
    "workload_id",
    "origin_cloud",
    "origin_region",
    "cache_policy",
    "request_profile_id",
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

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_MIGRATIONS_DIR = _REPO_ROOT / "migrations"

# SQLAlchemy Core table metadata, used by all read/write operations.
_metadata = MetaData()

_requests = Table(
    "requests",
    _metadata,
    Column("id", Text, primary_key=True),
    Column("recorded_at", Text, nullable=False),
    Column("environment", Text, nullable=False),
    Column("provider", Text, nullable=False),
    Column("model", Text, nullable=False),
    Column("outcome", Text, nullable=False),
    Column("input_tokens", Integer),
    Column("requested_max_output_tokens", Integer, nullable=False),
    Column("output_tokens", Integer),
    Column("input_price_per_1m", Float, nullable=False),
    Column("output_price_per_1m", Float, nullable=False),
    Column("input_cost", Float),
    Column("output_cost", Float),
    Column("total_cost", Float),
    Column("failed_after_ms", Float),
    Column("provider_request_id", Text),
    Column("workload_id", Text),
    Column("origin_cloud", Text),
    Column("origin_region", Text),
    Column("cache_policy", Text),
    Column("cached_input_tokens", Integer),
    Column("request_profile_id", Text),
    Column("cached_input_price_per_1m", Float),
    CheckConstraint(
        "environment IN ('test', 'prod')", name="ck_requests_environment"
    ),
    CheckConstraint(
        "outcome IN ('success', 'timeout', 'rate_limited', 'provider_error',"
        " 'transport_error', 'invalid_response')",
        name="ck_requests_outcome",
    ),
    CheckConstraint("input_tokens >= 0", name="ck_requests_input_tokens"),
    CheckConstraint(
        "requested_max_output_tokens >= 1",
        name="ck_requests_requested_max_output_tokens",
    ),
    CheckConstraint("output_tokens >= 0", name="ck_requests_output_tokens"),
    CheckConstraint(
        "input_price_per_1m >= 0", name="ck_requests_input_price_per_1m"
    ),
    CheckConstraint(
        "output_price_per_1m >= 0", name="ck_requests_output_price_per_1m"
    ),
    CheckConstraint("failed_after_ms >= 0", name="ck_requests_failed_after_ms"),
    CheckConstraint(
        "cache_policy IN ('disabled', 'enabled', 'provider_default', 'unknown')",
        name="ck_requests_cache_policy",
    ),
    CheckConstraint(
        "cached_input_tokens >= 0", name="ck_requests_cached_input_tokens"
    ),
    CheckConstraint(
        "cached_input_price_per_1m >= 0",
        name="ck_requests_cached_input_price_per_1m",
    ),
    CheckConstraint(
        "(outcome = 'success'"
        " AND input_tokens IS NOT NULL AND output_tokens IS NOT NULL"
        " AND input_cost IS NOT NULL AND output_cost IS NOT NULL"
        " AND total_cost IS NOT NULL AND failed_after_ms IS NULL)"
        " OR"
        " (outcome <> 'success'"
        " AND input_tokens IS NULL AND output_tokens IS NULL"
        " AND input_cost IS NULL AND output_cost IS NULL"
        " AND total_cost IS NULL AND failed_after_ms IS NOT NULL)",
        name="ck_requests_outcome_consistency",
    ),
)

_observations = Table(
    "observations",
    _metadata,
    Column("id", Integer, primary_key=True),
    Column("recorded_at", Text, nullable=False),
    Column("environment", Text, nullable=False),
    Column("provider", Text, nullable=False),
    Column("model", Text, nullable=False),
    Column("metric", Text, nullable=False),
    Column("value", Float, nullable=False),
    Column("request_id", Text, ForeignKey("requests.id")),
    CheckConstraint(
        "environment IN ('test', 'prod')", name="ck_observations_environment"
    ),
)

# Module-level engine cache keyed by database URL string.
# Engines are long-lived; the same engine is reused for all calls to the
# same database. This avoids pool-teardown overhead on every function call.
_engines: dict[str, Engine] = {}


def _redact_db_url(url: str) -> str:
    """Returns url with user:password@ stripped, for safe display and errors."""
    at = url.find("@")
    if at < 0:
        return url
    scheme_end = url.find("://")
    if scheme_end < 0:
        return url
    return url[: scheme_end + 3] + url[at + 1 :]


def connect(db_ref: pathlib.Path | str) -> Engine:
    """Returns a SQLAlchemy Engine for db_ref, creating/migrating as needed.

    The first call for a given database creates the engine and ensures the
    schema is at the current version. Subsequent calls return the cached engine
    without re-running migrations. For SQLite paths the parent directory is
    created if needed; for URL strings no filesystem operations are performed.

    Args:
        db_ref: A pathlib.Path for a local SQLite file, or a SQLAlchemy URL
            string ('sqlite:///...' or 'postgresql://...'). Paths are resolved
            to absolute form.

    Returns:
        A shared Engine. Callers must not call engine.dispose().

    Raises:
        RuntimeError: If the SQLite schema version is newer than this code,
            or if a PostgreSQL database has application tables but no Alembic
            revision record (fail-closed on unknown schema state).
    """
    if isinstance(db_ref, pathlib.Path):
        resolved = db_ref.resolve()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{resolved}"
    else:
        url = str(db_ref)
        if url.startswith("sqlite:///"):
            pathlib.Path(url[len("sqlite:///") :]).parent.mkdir(
                parents=True, exist_ok=True
            )
    if url not in _engines:
        if url.startswith("sqlite:///"):
            engine = create_engine(
                url, connect_args={"check_same_thread": False}
            )
        else:
            engine = create_engine(url)
        try:
            _ensure_schema(engine)
        except Exception:
            engine.dispose()
            raise
        _engines[url] = engine
    return _engines[url]


def _columns_of(conn: Connection, table: str) -> set[str]:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {row[1] for row in rows}


def _legacy_upgrade(engine: Engine) -> None:
    """Brings a pre-Alembic SQLite database up to SCHEMA_VERSION.

    Equivalent to the former _upgrade() function, but uses SQLAlchemy Core
    text() constructs. Runs entirely in one transaction so an upgrade is
    all-or-nothing. After this call, the database has the v7 schema but no
    Alembic alembic_version row; the caller must stamp it.

    Facts that were never recorded for older rows stay unknown (NULL or
    "unknown"); nothing is backfilled or guessed.
    """
    with engine.begin() as conn:
        version = conn.execute(text("PRAGMA user_version")).scalar() or 0
        if version == SCHEMA_VERSION:
            return

        if version < 1:
            cols = _columns_of(conn, "observations")
            if "value_ms" in cols:
                conn.execute(
                    text(
                        "ALTER TABLE observations RENAME COLUMN value_ms TO value"
                    )
                )
        if version < 2:
            if "request_id" not in _columns_of(conn, "observations"):
                conn.execute(
                    text(
                        "ALTER TABLE observations ADD COLUMN request_id TEXT"
                        " REFERENCES requests (id)"
                    )
                )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS observations_request"
                    " ON observations (request_id)"
                )
            )
        if version < 3:
            existing_requests_cols = _columns_of(conn, "requests")
            if not existing_requests_cols:
                # No requests table yet (v0/v1 databases): create the full
                # current schema directly; subsequent ADD COLUMN steps are
                # no-ops because all columns already exist.
                conn.execute(text(_REQUESTS_TABLE))
                # Ensure the unique index exists (normally created with the
                # observations table; idempotent via IF NOT EXISTS).
                conn.execute(
                    text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS observations_unique"
                        " ON observations"
                        " (recorded_at, environment, provider, model, metric)"
                    )
                )
            elif "outcome" not in existing_requests_cols:
                # v2 requests table (NOT NULL token/cost, no outcome column):
                # rebuild with outcome. Version-2 rows were all successful.
                conn.execute(
                    text(
                        _REQUESTS_TABLE.replace(
                            "IF NOT EXISTS requests", "requests_v3"
                        )
                    )
                )
                columns = ", ".join(_V2_REQUEST_COLUMNS)
                conn.execute(
                    text(
                        f"INSERT INTO requests_v3 ({columns}, outcome,"
                        f" failed_after_ms)"
                        f" SELECT {columns}, 'success', NULL FROM requests"
                    )
                )
                conn.execute(text("DROP TABLE requests"))
                conn.execute(
                    text("ALTER TABLE requests_v3 RENAME TO requests")
                )
        if version < 4 and "provider_request_id" not in _columns_of(
            conn, "requests"
        ):
            conn.execute(
                text("ALTER TABLE requests ADD COLUMN provider_request_id TEXT")
            )
        if version < 5:
            existing = _columns_of(conn, "requests")
            for column in ("workload_id", "origin_cloud", "origin_region"):
                if column not in existing:
                    conn.execute(
                        text(f"ALTER TABLE requests ADD COLUMN {column} TEXT")
                    )
        if version < 6:
            if "cache_policy" not in _columns_of(conn, "requests"):
                conn.execute(
                    text(
                        "ALTER TABLE requests ADD COLUMN cache_policy TEXT"
                        " CHECK (cache_policy IN ("
                        "'disabled', 'enabled', 'provider_default', 'unknown'))"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE requests ADD COLUMN cached_input_tokens"
                        " INTEGER CHECK (cached_input_tokens >= 0)"
                    )
                )
            conn.execute(
                text(
                    "UPDATE requests SET cache_policy = 'unknown'"
                    " WHERE cache_policy IS NULL"
                )
            )
        if version < 7:
            existing = _columns_of(conn, "requests")
            if "request_profile_id" not in existing:
                conn.execute(
                    text(
                        "ALTER TABLE requests ADD COLUMN request_profile_id TEXT"
                    )
                )
            if "cached_input_price_per_1m" not in existing:
                conn.execute(
                    text(
                        "ALTER TABLE requests ADD COLUMN"
                        " cached_input_price_per_1m REAL"
                        " CHECK (cached_input_price_per_1m >= 0)"
                    )
                )
        # Ensure the observations table and its indexes exist.  A v3+ database
        # built without any observations rows may have no observations table.
        if not _columns_of(conn, "observations"):
            conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS observations ("
                    "id INTEGER PRIMARY KEY,"
                    " recorded_at TEXT NOT NULL,"
                    " environment TEXT NOT NULL"
                    " CHECK (environment IN ('test', 'prod')),"
                    " provider TEXT NOT NULL,"
                    " model TEXT NOT NULL,"
                    " metric TEXT NOT NULL,"
                    " value REAL NOT NULL,"
                    " request_id TEXT REFERENCES requests (id)"
                    ")"
                )
            )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS observations_unique"
                " ON observations"
                " (recorded_at, environment, provider, model, metric)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS observations_request"
                " ON observations (request_id)"
            )
        )
        conn.execute(text(f"PRAGMA user_version = {SCHEMA_VERSION}"))


def _ensure_schema(engine: Engine) -> None:
    """Creates or migrates the schema to the current version.

    For SQLite:
        Fresh database: Alembic creates all tables and sets PRAGMA user_version.
        Pre-Alembic database (v0–v7): legacy upgrade bridge then Alembic stamp.
        Alembic-managed: applies any pending revisions.
    For PostgreSQL:
        Fresh database: Alembic creates all tables.
        Tables with no alembic_version row: raises RuntimeError (fail-closed).
        Alembic-managed: applies any pending revisions.

    The Alembic connection is passed via config.attributes["connection"] so
    the database URL is never serialised into a config string or log line.
    This prevents credential exposure and avoids ConfigParser interpolation
    errors on percent-encoded characters in passwords.

    Raises:
        RuntimeError: If the SQLite schema version is newer than this code,
            or if PostgreSQL has application tables but no Alembic revision.
    """
    from alembic import command
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext

    dialect = engine.dialect.name
    with engine.connect() as conn:
        if dialect == "sqlite":
            version = conn.execute(text("PRAGMA user_version")).scalar() or 0
            if version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"Database schema version {version} is newer than this code"
                    f" supports ({SCHEMA_VERSION}). Update llm-metrics."
                )
        else:
            version = 0
        from sqlalchemy import inspect as _sa_inspect

        insp = _sa_inspect(conn)
        has_any_table = insp.has_table("requests") or insp.has_table(
            "observations"
        )
        context = MigrationContext.configure(conn)
        current_rev = context.get_current_revision()

    # Build Alembic config without setting sqlalchemy.url as a config string.
    # Credentials are kept out of config interpolation and log output by
    # passing a live connection via config.attributes["connection"] instead.
    alembic_cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))

    if current_rev is None:
        if has_any_table:
            if dialect == "sqlite":
                # Pre-Alembic SQLite: run legacy upgrade if needed, then stamp.
                if version < SCHEMA_VERSION:
                    _legacy_upgrade(engine)
                with engine.connect() as conn:
                    alembic_cfg.attributes["connection"] = conn
                    command.stamp(alembic_cfg, "head")
            else:
                # Fail closed: PostgreSQL with application tables but no
                # Alembic revision. Silently stamping would trust an unknown
                # schema; require manual inspection and stamping instead.
                raise RuntimeError(
                    "PostgreSQL database has existing tables but no Alembic"
                    " revision record. Cannot safely assume the schema matches"
                    " the current version. Inspect the schema and run"
                    " 'alembic stamp <revision>' manually if it is correct."
                )
        else:
            # Fresh database: let Alembic create all tables.
            with engine.connect() as conn:
                alembic_cfg.attributes["connection"] = conn
                command.upgrade(alembic_cfg, "head")
            if dialect == "sqlite":
                # Keep PRAGMA user_version in sync so legacy readers still work.
                with engine.begin() as conn:
                    conn.execute(
                        text(f"PRAGMA user_version = {SCHEMA_VERSION}")
                    )
    else:
        # Already Alembic-managed: apply any pending revisions.
        with engine.connect() as conn:
            alembic_cfg.attributes["connection"] = conn
            command.upgrade(alembic_cfg, "head")


def format_timestamp(moment: datetime.datetime) -> str:
    """Formats an aware datetime as stored `recorded_at` text (UTC)."""
    return moment.astimezone(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )


def _observation_values(
    recorded_at: str, environment: str, result: dict, request_id: str | None
) -> dict:
    return {
        "recorded_at": recorded_at,
        "environment": environment,
        "provider": result["provider"],
        "model": result["model"],
        "metric": result["metric"],
        "value": result["value"],
        "request_id": request_id,
    }


def save_request(
    db_path: pathlib.Path | str, request: dict, results: list[dict], environment: str
) -> str:
    """Saves one benchmark attempt and its metric observations atomically.

    The request row and all observations share one timestamp and are written
    in one transaction: either everything is saved or nothing.

    Args:
        db_path: Database file.
        request: Every `_REQUEST_COLUMNS` key except "id", "recorded_at", and
            "environment", with unknown facts of a failed attempt as None.
            "provider_request_id", "cached_input_tokens" and
            "cached_input_price_per_1m" may be omitted (stored as NULL).
            Extra keys (e.g. "diagnostics") are ignored.
        results: Metric observations; must be empty for a failed attempt.
        environment: "test" or "prod".

    Returns:
        The new request's id.

    Raises:
        ValueError: If a failed attempt has observations, or a required
            condition (workload, origin, cache policy, request profile) is
            missing or empty. Nothing is written.
        sqlalchemy.exc.IntegrityError: If facts violate the table's CHECKs.
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
        "cached_input_price_per_1m": None,
        **request,
        "id": request_id,
        "recorded_at": recorded_at,
        "environment": environment,
    }
    values = {column: row.get(column) for column in _REQUEST_COLUMNS}
    observations = [
        _observation_values(recorded_at, environment, result, request_id)
        for result in results
    ]
    engine = connect(db_path)
    with engine.begin() as conn:
        conn.execute(_requests.insert().values(**values))
        if observations:
            conn.execute(_observations.insert(), observations)
    return request_id


def save_new_observations(
    db_path: pathlib.Path | str,
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
        _observation_values(
            format_timestamp(recorded_at), environment, result, None
        )
        for recorded_at, result in observations
    ]
    engine = connect(db_path)
    # on_conflict_do_nothing: duplicate (recorded_at, environment, provider,
    # model, metric) rows are silently skipped, making seeding idempotent.
    if engine.dialect.name == "postgresql":
        stmt = _pg_insert(_observations).on_conflict_do_nothing()
    else:
        stmt = _sqlite_insert(_observations).on_conflict_do_nothing()
    with engine.begin() as conn:
        result = conn.execute(stmt, rows)
        return result.rowcount


def load_observations(
    db_path: pathlib.Path | str,
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
    o = _observations
    stmt = (
        select(o.c.recorded_at, o.c.value)
        .where(
            o.c.environment == environment,
            o.c.provider == provider,
            o.c.model == model,
            o.c.metric == metric,
            o.c.recorded_at >= format_timestamp(start),
            o.c.recorded_at <= format_timestamp(end),
        )
        .order_by(o.c.recorded_at, o.c.id)
    )
    if cache_policy is not None:
        subq = (
            select(_requests.c.id)
            .where(_requests.c.cache_policy == cache_policy)
            .scalar_subquery()
        )
        stmt = stmt.where(o.c.request_id.in_(subq))
    engine = connect(db_path)
    with engine.connect() as conn:
        return [(row.recorded_at, row.value) for row in conn.execute(stmt)]


def _request_dicts(conn: Connection, where_clause) -> list[dict]:
    """Loads requests matching `where_clause`, newest first, with their metrics.

    Args:
        conn: Open SQLAlchemy connection.
        where_clause: A SQLAlchemy column expression filtering on `_requests`.

    Returns:
        One dict per request with every `_REQUEST_COLUMNS` key plus "metrics"
        ({metric: value} of its linked observations; empty for failures).
    """
    r = _requests
    o = _observations
    stmt = (
        select(
            *[r.c[col] for col in _REQUEST_COLUMNS],
            o.c.metric,
            o.c.value,
        )
        .select_from(r.outerjoin(o, o.c.request_id == r.c.id))
        .where(where_clause)
        .order_by(r.c.recorded_at.desc(), r.c.id, o.c.id)
    )
    rows = conn.execute(stmt).fetchall()
    requests: dict[str, dict] = {}
    for row in rows:
        req = requests.setdefault(
            row.id,
            {
                **{col: getattr(row, col) for col in _REQUEST_COLUMNS},
                "metrics": {},
            },
        )
        if row.metric is not None:
            req["metrics"][row.metric] = row.value
    return list(requests.values())


def load_request(db_path: pathlib.Path | str, request_id: str) -> dict | None:
    """Returns one request with its metrics (see `_request_dicts`), or None."""
    engine = connect(db_path)
    with engine.connect() as conn:
        found = _request_dicts(conn, _requests.c.id == request_id)
    return found[0] if found else None


def load_recent_requests(
    db_path: pathlib.Path | str, environment: str, limit: int
) -> list[dict]:
    """Returns the `limit` most recent requests in `environment`, newest first.

    Each request includes its metrics; see `_request_dicts`.
    """
    subq = (
        select(_requests.c.id)
        .where(_requests.c.environment == environment)
        .order_by(_requests.c.recorded_at.desc(), _requests.c.id)
        .limit(limit)
        .scalar_subquery()
    )
    engine = connect(db_path)
    with engine.connect() as conn:
        return _request_dicts(conn, _requests.c.id.in_(subq))


def count_outcomes(
    db_path: pathlib.Path | str,
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
    r = _requests
    stmt = (
        select(r.c.outcome, func.count().label("cnt"))
        .where(
            r.c.environment == environment,
            r.c.provider == provider,
            r.c.model == model,
            r.c.recorded_at >= format_timestamp(start),
            r.c.recorded_at <= format_timestamp(end),
        )
        .group_by(r.c.outcome)
    )
    engine = connect(db_path)
    with engine.connect() as conn:
        return {row.outcome: row.cnt for row in conn.execute(stmt)}


def spend_by_model(
    db_path: pathlib.Path | str,
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
    r = _requests
    is_success = r.c.outcome == "success"
    stmt = (
        select(
            r.c.provider,
            r.c.model,
            func.count().label("attempts"),
            func.sum(case((is_success, 1), else_=0)).label("successful_calls"),
            func.sum(case((~is_success, 1), else_=0)).label("failed_attempts"),
            func.sum(
                case((is_success, r.c.input_tokens), else_=None)
            ).label("input_tokens"),
            func.sum(
                case((is_success, r.c.output_tokens), else_=None)
            ).label("output_tokens"),
            func.sum(
                case((is_success, r.c.total_cost), else_=None)
            ).label("total_cost"),
        )
        .where(
            r.c.environment == environment,
            r.c.recorded_at >= format_timestamp(start),
            r.c.recorded_at <= format_timestamp(end),
        )
        .group_by(r.c.provider, r.c.model)
        .order_by(
            func.sum(
                case((is_success, r.c.total_cost), else_=None)
            ).is_(None),
            func.sum(
                case((is_success, r.c.total_cost), else_=None)
            ).desc(),
            r.c.provider,
            r.c.model,
        )
    )
    engine = connect(db_path)
    with engine.connect() as conn:
        return [row._asdict() for row in conn.execute(stmt)]
