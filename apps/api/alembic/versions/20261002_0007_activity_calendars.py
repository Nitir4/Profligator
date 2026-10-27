"""Add public submission calendars and source difficulty counts."""

from alembic import op
import sqlalchemy as sa

revision = "20261002_0007"
down_revision = "20261002_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("platform_profiles") as batch:
        batch.add_column(sa.Column("source_difficulty_counts", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("activity_status", sa.String(32), nullable=False, server_default="unsupported"))
        batch.add_column(sa.Column("activity_available_years", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("activity_error", sa.String(64), nullable=True))
    op.create_table(
        "profile_activity_calendars",
        sa.Column("platform_profile_id", sa.String(36), sa.ForeignKey("platform_profiles.id"), primary_key=True),
        sa.Column("year", sa.Integer(), primary_key=True),
        sa.Column("days", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("profile_activity_calendars")
    with op.batch_alter_table("platform_profiles") as batch:
        batch.drop_column("activity_error")
        batch.drop_column("activity_available_years")
        batch.drop_column("activity_status")
        batch.drop_column("source_difficulty_counts")
