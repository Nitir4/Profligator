"""Add soft-disconnect state to linked profiles.

Revision ID: 20260925_0002
Revises: 20260925_0001
Create Date: 2026-09-25
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260925_0002"
down_revision: str | None = "20260925_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "platform_profiles",
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_platform_profiles_disconnected_at",
        "platform_profiles",
        ["disconnected_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_platform_profiles_disconnected_at", table_name="platform_profiles")
    op.drop_column("platform_profiles", "disconnected_at")
