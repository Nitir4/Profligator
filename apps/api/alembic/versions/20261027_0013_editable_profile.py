"""Editable account details and persistent, processed profile photos."""
from alembic import op
import sqlalchemy as sa

revision = "20261027_0013"
down_revision = "20261013_0012"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("display_name", sa.String(80), server_default="", nullable=False))
    op.add_column("users", sa.Column("bio", sa.String(280), server_default="", nullable=False))
    op.add_column("users", sa.Column("avatar_revision", sa.String(64)))
    op.create_index("uq_users_handle_lower", "users", [sa.text("lower(handle)")], unique=True)
    op.create_table("user_avatars", sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), primary_key=True),
                    sa.Column("data", sa.LargeBinary(), nullable=False))


def downgrade():
    op.drop_table("user_avatars")
    op.drop_index("uq_users_handle_lower", table_name="users")
    op.drop_column("users", "avatar_revision")
    op.drop_column("users", "bio")
    op.drop_column("users", "display_name")
