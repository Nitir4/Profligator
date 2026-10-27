"""Implement report entities, sharing consent, and matching provenance."""

from alembic import op
import sqlalchemy as sa
from datetime import UTC, datetime
from uuid import uuid4

revision = "20261001_0004"
down_revision = "20260925_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("role", sa.String(32), nullable=False, server_default="candidate"))
        batch.add_column(sa.Column("auth_provider", sa.String(32), nullable=False, server_default="password"))
        batch.add_column(sa.Column("is_sharing_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("share_token", sa.String(64)))
        batch.create_unique_constraint("uq_users_share_token", ["share_token"])
    with op.batch_alter_table("platform_profiles") as batch:
        batch.add_column(sa.Column("source_total_solved", sa.Integer()))
        batch.add_column(sa.Column("rating", sa.Integer()))
        batch.add_column(sa.Column("rank", sa.String(128)))
        batch.add_column(sa.Column("history_complete", sa.Boolean()))
    op.add_column("sync_runs", sa.Column("matching_status", sa.String(32)))
    op.create_table(
        "unique_clusters",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("base_problem_title", sa.String(512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_unique_clusters_user_id", "unique_clusters", ["user_id"])
    with op.batch_alter_table("coding_records") as batch:
        batch.add_column(sa.Column("cluster_id", sa.String(36)))
        batch.add_column(sa.Column("statement", sa.Text()))
        batch.add_column(sa.Column("submission_url", sa.String(1024)))
        batch.add_column(sa.Column("contest_rating", sa.Integer()))
        batch.add_column(sa.Column("global_rank", sa.Integer()))
        batch.add_column(sa.Column("similarity_score", sa.Float()))
        batch.add_column(sa.Column("matching_state", sa.String(32), nullable=False, server_default="pending"))
        batch.create_foreign_key("fk_coding_records_cluster", "unique_clusters", ["cluster_id"], ["id"])
        batch.create_index("ix_coding_records_cluster_id", ["cluster_id"])
    # Existing records become distinct singleton clusters until evidence is available.
    connection = op.get_bind()
    records = connection.execute(sa.text(
        "SELECT r.id, r.title, p.user_id FROM coding_records r "
        "JOIN platform_profiles p ON p.id=r.platform_profile_id "
        "WHERE r.kind='problem' AND r.status='solved'"
    )).all()
    clusters = sa.table("unique_clusters", sa.column("id"), sa.column("user_id"),
                        sa.column("base_problem_title"), sa.column("created_at", sa.DateTime(timezone=True)))
    for record in records:
        cluster_id = str(uuid4())
        connection.execute(clusters.insert().values(id=cluster_id, user_id=record.user_id,
                           base_problem_title=record.title, created_at=datetime.now(UTC)))
        connection.execute(sa.text("UPDATE coding_records SET cluster_id=:cluster_id, matching_state='missing_statement' WHERE id=:id"),
                           {"cluster_id": cluster_id, "id": record.id})
    connection.execute(sa.text("UPDATE platform_profiles SET verification_state='unverified' WHERE connector_mode='official_api'"))
    op.create_table(
        "match_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("record_id", sa.String(36), sa.ForeignKey("coding_records.id"), nullable=False),
        sa.Column("candidate_record_id", sa.String(36), sa.ForeignKey("coding_records.id"), nullable=False),
        sa.Column("input_checksum", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128)),
        sa.Column("duplicate", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_match_decisions_record_id", "match_decisions", ["record_id"])


def downgrade() -> None:
    op.drop_table("match_decisions")
    with op.batch_alter_table("coding_records") as batch:
        batch.drop_index("ix_coding_records_cluster_id")
        batch.drop_constraint("fk_coding_records_cluster", type_="foreignkey")
        for column in ("matching_state", "similarity_score", "global_rank", "contest_rating", "submission_url", "statement", "cluster_id"):
            batch.drop_column(column)
    op.drop_table("unique_clusters")
    op.drop_column("sync_runs", "matching_status")
    with op.batch_alter_table("platform_profiles") as batch:
        for column in ("history_complete", "rank", "rating", "source_total_solved"):
            batch.drop_column(column)
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("uq_users_share_token", type_="unique")
        for column in ("share_token", "is_sharing_enabled", "auth_provider", "role"):
            batch.drop_column(column)
