"""Baseline: schema version 7.

This revision defines the full v7 schema — the starting point for all
Alembic-managed migrations. It creates the schema from scratch on a fresh
database. Existing pre-Alembic databases are stamped to this revision by
storage._ensure_schema() without running this DDL (their tables already
exist from the legacy v0→v7 upgrade path).

Revision ID: f1a2b3c4d5e6
Revises:
Create Date: 2026-11-03
"""

import sqlalchemy as sa
from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "requests",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.Text(), nullable=False),
        sa.Column("environment", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("requested_max_output_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("input_price_per_1m", sa.Float(), nullable=False),
        sa.Column("output_price_per_1m", sa.Float(), nullable=False),
        sa.Column("input_cost", sa.Float(), nullable=True),
        sa.Column("output_cost", sa.Float(), nullable=True),
        sa.Column("total_cost", sa.Float(), nullable=True),
        sa.Column("failed_after_ms", sa.Float(), nullable=True),
        sa.Column("provider_request_id", sa.Text(), nullable=True),
        sa.Column("workload_id", sa.Text(), nullable=True),
        sa.Column("origin_cloud", sa.Text(), nullable=True),
        sa.Column("origin_region", sa.Text(), nullable=True),
        sa.Column("cache_policy", sa.Text(), nullable=True),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=True),
        sa.Column("request_profile_id", sa.Text(), nullable=True),
        sa.Column("cached_input_price_per_1m", sa.Float(), nullable=True),
        sa.CheckConstraint(
            "environment IN ('test', 'prod')",
            name="ck_requests_environment",
        ),
        sa.CheckConstraint(
            "outcome IN ('success', 'timeout', 'rate_limited', 'provider_error',"
            " 'transport_error', 'invalid_response')",
            name="ck_requests_outcome",
        ),
        sa.CheckConstraint("input_tokens >= 0", name="ck_requests_input_tokens"),
        sa.CheckConstraint(
            "requested_max_output_tokens >= 1",
            name="ck_requests_requested_max_output_tokens",
        ),
        sa.CheckConstraint(
            "output_tokens >= 0", name="ck_requests_output_tokens"
        ),
        sa.CheckConstraint(
            "input_price_per_1m >= 0", name="ck_requests_input_price_per_1m"
        ),
        sa.CheckConstraint(
            "output_price_per_1m >= 0", name="ck_requests_output_price_per_1m"
        ),
        sa.CheckConstraint(
            "failed_after_ms >= 0", name="ck_requests_failed_after_ms"
        ),
        sa.CheckConstraint(
            "cache_policy IN ('disabled', 'enabled', 'provider_default', 'unknown')",
            name="ck_requests_cache_policy",
        ),
        sa.CheckConstraint(
            "cached_input_tokens >= 0", name="ck_requests_cached_input_tokens"
        ),
        sa.CheckConstraint(
            "cached_input_price_per_1m >= 0",
            name="ck_requests_cached_input_price_per_1m",
        ),
        sa.CheckConstraint(
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "observations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.Text(), nullable=False),
        sa.Column(
            "environment",
            sa.Text(),
            sa.CheckConstraint(
                "environment IN ('test', 'prod')",
                name="ck_observations_environment",
            ),
            nullable=False,
        ),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("metric", sa.Text(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["requests.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "observations_unique",
        "observations",
        ["recorded_at", "environment", "provider", "model", "metric"],
        unique=True,
    )
    op.create_index(
        "observations_request",
        "observations",
        ["request_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("observations_request", table_name="observations")
    op.drop_index("observations_unique", table_name="observations")
    op.drop_table("observations")
    op.drop_table("requests")
