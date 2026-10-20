"""Account administration metadata; preserve unknown historical timestamps and all records."""

from alembic import op
import sqlalchemy as sa

revision = "r846247abd17"
down_revision = "q735136fac16"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("first_name", "last_name"):
        op.add_column("users", sa.Column(name, sa.String(100), nullable=True))
    for name in ("created_at", "updated_at", "deactivated_at", "last_session_at"):
        op.add_column("users", sa.Column(name, sa.Float(), nullable=True))
    op.add_column("users", sa.Column("admin_revision", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    if op.get_bind().scalar(
        sa.text(
            "SELECT count(*) FROM users WHERE first_name IS NOT NULL OR last_name IS NOT NULL OR created_at IS NOT NULL OR updated_at IS NOT NULL OR deactivated_at IS NOT NULL OR last_session_at IS NOT NULL OR admin_revision != 0"
        )
    ):
        raise RuntimeError("Account administration history exists; restore a verified backup rather than discard it.")
    with op.batch_alter_table("users") as batch:
        for name in (
            "first_name",
            "last_name",
            "created_at",
            "updated_at",
            "deactivated_at",
            "last_session_at",
            "admin_revision",
        ):
            batch.drop_column(name)
