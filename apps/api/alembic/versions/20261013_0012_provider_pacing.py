"""Coordinate provider request spacing across API and worker processes."""
from alembic import op
import sqlalchemy as sa
revision = "20261013_0012"
down_revision = "20261013_0011"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("provider_request_windows",
        sa.Column("key", sa.String(160), primary_key=True),
        sa.Column("next_request_at", sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table("provider_request_windows")
