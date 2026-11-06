"""Step 020 helper: migrate, verify and export the temporary pilot database.

Runs inside the production image (mounted read-only at /tools), connected to a
local Cloud SQL Auth Proxy container, e.g.:

    docker run --rm --network <net> -e PYTHONPATH=/app -v <secret-dir>:/secret:ro -v $PWD/scripts/gcp:/tools:ro \
            -v <out>:/out <image> python /tools/020_db_tool.py <migrate|verify|export> --host proxy

Credentials come from files in /secret (db_user, db_password, db_name) and are
assembled with sqlalchemy.engine.URL.create, so they are never printed, never
appear in a process argument list, and are percent-encoded correctly. Output is
limited to measurement metadata already stored by the benchmark: the schema has
no prompt, response, key or raw provider error columns.
"""

import argparse
import csv
import datetime
import hashlib
import json
import pathlib
import sys

from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.engine import URL

from llm_metrics import storage

_SECRET_DIR = pathlib.Path("/secret")
_OUT_DIR = pathlib.Path("/out")
# Stable column order for the export. It mirrors storage.py's v7 tables, so a
# restore can use COPY ... CSV HEADER into freshly migrated tables.
_REQUEST_COLUMNS = (
    "id", "recorded_at", "environment", "provider", "model", "outcome",
    "input_tokens", "requested_max_output_tokens", "output_tokens",
    "input_price_per_1m", "output_price_per_1m", "input_cost", "output_cost",
    "total_cost", "failed_after_ms", "provider_request_id", "workload_id",
    "origin_cloud", "origin_region", "cache_policy", "cached_input_tokens",
    "request_profile_id", "cached_input_price_per_1m",
)  # fmt: skip
_OBSERVATION_COLUMNS = (
    "id", "recorded_at", "environment", "provider", "model", "metric", "value",
    "request_id",
)  # fmt: skip


def _url(host: str, port: int) -> str:
    read = lambda name: (_SECRET_DIR / name).read_text().strip()
    return URL.create(
            "postgresql+psycopg2",
            username=read("db_user"),
            password=read("db_password"),
            host=host,
            port=port,
            database=read("db_name"),
    ).render_as_string(hide_password=False)


def _schema_report(conn) -> dict:
    revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    tables = sorted(
            conn.execute(
                    text(
                            "SELECT table_name FROM information_schema.tables"
                            " WHERE table_schema = 'public'"
                    )
            ).scalars()
    )
    return {
            "alembic_revision": revision,
            "tables": tables,
            "requests": conn.execute(text("SELECT count(*) FROM requests")).scalar(),
            "observations": conn.execute(
                    text("SELECT count(*) FROM observations")
            ).scalar(),
            "server_version": conn.execute(text("SHOW server_version")).scalar(),
    }


def _migrate(url: str) -> None:
    # storage.connect() runs Alembic to head on a fresh PostgreSQL database and
    # fails closed on unknown schema state; it is the same path the job uses.
    engine = storage.connect(url)
    with engine.connect() as conn:
        print(json.dumps(_schema_report(conn), indent=2))


def _rows(conn, table: str, columns: tuple[str, ...]) -> list[dict]:
    query = text(f"SELECT {', '.join(columns)} FROM {table} ORDER BY id")
    return [dict(row._mapping) for row in conn.execute(query)]


def _verify(url: str) -> None:
    engine = create_engine(url)
    with engine.connect() as conn:
        report = _schema_report(conn)
        report["request_rows"] = _rows(conn, "requests", _REQUEST_COLUMNS)
        report["observation_rows"] = _rows(
                conn, "observations", _OBSERVATION_COLUMNS
        )
    engine.dispose()
    print(json.dumps(report, indent=2, default=str))


def _write_csv(path: pathlib.Path, columns, rows) -> str:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            # Unknown stays an empty cell (NULL on restore), never a fabricated 0.
            writer.writerow({k: "" if v is None else v for k, v in row.items()})
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _export(url: str, run_id: str) -> None:
    engine = create_engine(url)
    with engine.connect() as conn:
        report = _schema_report(conn)
        requests = _rows(conn, "requests", _REQUEST_COLUMNS)
        observations = _rows(conn, "observations", _OBSERVATION_COLUMNS)
    engine.dispose()
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    sums = {
            "requests.csv": _write_csv(
                    _OUT_DIR / "requests.csv", _REQUEST_COLUMNS, requests
            ),
            "observations.csv": _write_csv(
                    _OUT_DIR / "observations.csv", _OBSERVATION_COLUMNS, observations
            ),
    }
    manifest = {
            "step": "020",
            "run_id": run_id,
            "exported_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "schema": "llm_metrics v7",
            "alembic_revision": report["alembic_revision"],
            "postgres_server_version": report["server_version"],
            "row_counts": {"requests": len(requests), "observations": len(observations)},
            "columns": {
                    "requests.csv": list(_REQUEST_COLUMNS),
                    "observations.csv": list(_OBSERVATION_COLUMNS),
            },
            "sha256": sums,
            "restore": (
                    "Migrate a fresh database to the alembic_revision via"
                    " storage.connect(), then \\copy requests FROM 'requests.csv' CSV"
                    " HEADER; \\copy observations FROM 'observations.csv' CSV HEADER"
                    " (FK order); then SELECT setval(pg_get_serial_sequence("
                    "'observations','id'), (SELECT max(id) FROM observations))."
            ),
            "excluded": "prompts, responses, credentials, database URLs, raw provider error bodies (not stored by schema)",
    }
    (_OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest["row_counts"]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("migrate", "verify", "export"))
    parser.add_argument("--host", default="proxy")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--run-id", default="")
    args = parser.parse_args()
    url = _url(args.host, args.port)
    if args.action == "migrate":
        _migrate(url)
    elif args.action == "verify":
        _verify(url)
    else:
        if not args.run_id:
            parser.error("export requires --run-id")
        _export(url, args.run_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
