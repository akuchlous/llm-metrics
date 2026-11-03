"""Alembic migration environment.

Supports both offline (SQL script generation) and online (live database)
migration modes. The database URL is supplied programmatically by
storage._ensure_schema() so that the correct engine is always used.
"""

from alembic import context
from sqlalchemy import create_engine

config = context.config


def run_migrations_offline() -> None:
    """Run migrations emitting SQL to stdout (no live connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    # storage._ensure_schema() may pass a pre-existing connection via
    # config.attributes; otherwise create a fresh engine from the URL.
    connectable = config.attributes.get("connection")
    if connectable is not None:
        context.configure(connection=connectable)
        with context.begin_transaction():
            context.run_migrations()
    else:
        url = config.get_main_option("sqlalchemy.url")
        engine = create_engine(url)
        with engine.connect() as connection:
            context.configure(connection=connection)
            with context.begin_transaction():
                context.run_migrations()
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
