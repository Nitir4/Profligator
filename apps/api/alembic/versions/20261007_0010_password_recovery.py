"""Add expiring password recovery tokens and authentication invalidation.

Revision ID: 20261007_0010
Revises: 20261003_0009
"""
from alembic import op
import sqlalchemy as sa

revision = "20261007_0010"
down_revision = "20261003_0009"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("auth_version", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("refresh_sessions", sa.Column("auth_version", sa.Integer(), nullable=False, server_default="0"))
    op.create_table("password_reset_tokens",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("auth_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])
    op.create_table("password_reset_rate_limits",
        sa.Column("key_hash", sa.String(64), primary_key=True),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requests", sa.Integer(), nullable=False),
    )


def downgrade():
    op.drop_table("password_reset_rate_limits")
    op.drop_table("password_reset_tokens")
    with op.batch_alter_table("refresh_sessions") as batch:
        batch.drop_column("auth_version")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("auth_version")
