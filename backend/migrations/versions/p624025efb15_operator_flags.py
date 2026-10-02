"""Persist batch operator intent and retain deleted rule evidence."""

from alembic import op
import sqlalchemy as sa

revision = "p624025efb15"
down_revision = "o513914dea14"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("upload_batches") as batch:
        batch.add_column(sa.Column("employee_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_batch_employee", "employees", ["employee_id"], ["id"])
    op.add_column("flag_rules", sa.Column("deleted_at", sa.Float(), nullable=True))


def downgrade():
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT count(*) FROM upload_batches WHERE employee_id IS NOT NULL")) or bind.scalar(
        sa.text("SELECT count(*) FROM flag_rules WHERE deleted_at IS NOT NULL")
    ):
        raise RuntimeError("Cannot discard batch operator intent or rule deletion history. Restore a verified backup.")
    with op.batch_alter_table("flag_rules") as batch:
        batch.drop_column("deleted_at")
    with op.batch_alter_table("upload_batches") as batch:
        batch.drop_constraint("fk_batch_employee", type_="foreignkey")
        batch.drop_column("employee_id")
