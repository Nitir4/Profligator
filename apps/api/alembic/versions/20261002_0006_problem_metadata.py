"""Persist public problem enrichment progress between syncs and workers."""

from alembic import op
import sqlalchemy as sa

revision = "20261002_0006"
down_revision = "20261002_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "problem_metadata",
        sa.Column("provider", sa.String(32), primary_key=True),
        sa.Column("source_id", sa.String(160), primary_key=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("problem_metadata")
