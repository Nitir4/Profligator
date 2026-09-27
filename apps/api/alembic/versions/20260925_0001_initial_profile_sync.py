"""Create initial profile aggregation tables.

Revision ID: 20260925_0001
Revises:
Create Date: 2026-09-25
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260925_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("handle", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("handle"),
    )
    op.create_table(
        "platform_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("public_handle", sa.String(length=128), nullable=False),
        sa.Column("canonical_url", sa.String(length=512), nullable=False),
        sa.Column("verification_state", sa.String(length=32), nullable=False),
        sa.Column("connector_mode", sa.String(length=32), nullable=False),
        sa.Column("last_successful_sync", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "platform", "public_handle", name="uq_profile_identity"),
    )
    op.create_index("ix_platform_profiles_platform", "platform_profiles", ["platform"])
    op.create_index("ix_platform_profiles_user_id", "platform_profiles", ["user_id"])
    op.create_table(
        "sync_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("platform_profile_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("records_seen", sa.Integer(), nullable=False),
        sa.Column("records_written", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["platform_profile_id"], ["platform_profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sync_runs_platform_profile_id", "sync_runs", ["platform_profile_id"])
    op.create_table(
        "coding_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("platform_profile_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=160), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("canonical_url", sa.String(length=1024), nullable=False),
        sa.Column("difficulty", sa.String(length=64), nullable=True),
        sa.Column("topics", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_payload_checksum", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["platform_profile_id"], ["platform_profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "platform_profile_id", "source_id", "kind", name="uq_profile_source_record"
        ),
    )
    op.create_index("ix_coding_records_difficulty", "coding_records", ["difficulty"])
    op.create_index("ix_coding_records_occurred_at", "coding_records", ["occurred_at"])
    op.create_index(
        "ix_coding_records_platform_profile_id", "coding_records", ["platform_profile_id"]
    )
    op.create_index("ix_coding_records_title", "coding_records", ["title"])


def downgrade() -> None:
    op.drop_index("ix_coding_records_title", table_name="coding_records")
    op.drop_index("ix_coding_records_platform_profile_id", table_name="coding_records")
    op.drop_index("ix_coding_records_occurred_at", table_name="coding_records")
    op.drop_index("ix_coding_records_difficulty", table_name="coding_records")
    op.drop_table("coding_records")
    op.drop_index("ix_sync_runs_platform_profile_id", table_name="sync_runs")
    op.drop_table("sync_runs")
    op.drop_index("ix_platform_profiles_user_id", table_name="platform_profiles")
    op.drop_index("ix_platform_profiles_platform", table_name="platform_profiles")
    op.drop_table("platform_profiles")
    op.drop_table("users")
