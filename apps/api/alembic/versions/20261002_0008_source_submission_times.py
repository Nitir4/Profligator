"""Preserve unzoned source submission times without inventing UTC instants."""

from alembic import op
import sqlalchemy as sa

revision = "20261002_0008"
down_revision = "20261002_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("coding_records", sa.Column("source_solved_at", sa.String(32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("coding_records") as batch:
        batch.drop_column("source_solved_at")
