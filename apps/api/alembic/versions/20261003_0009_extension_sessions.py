"""Add scoped browser-extension sessions.

Revision ID: 20261003_0009
Revises: 20261002_0008
"""
from alembic import op
import sqlalchemy as sa

revision = "20261003_0009"
down_revision = "20261002_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("extension_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_extension_sessions_user_id", "extension_sessions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_extension_sessions_user_id", table_name="extension_sessions")
    op.drop_table("extension_sessions")
