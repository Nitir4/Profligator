"""Add independent email and coding-profile ownership challenges."""
from alembic import op
import sqlalchemy as sa

revision = "20261013_0011"
down_revision = "20261007_0010"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("verification_tokens",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("target", sa.String(320), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("auth_version", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_verification_tokens_user_id", "verification_tokens", ["user_id"])
    op.create_table("verified_emails",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("verified_emails")
    op.drop_table("verification_tokens")
