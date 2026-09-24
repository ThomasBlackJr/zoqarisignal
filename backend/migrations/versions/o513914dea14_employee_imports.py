"""Employee identifiers and scoped expiring import previews."""

from alembic import op
import sqlalchemy as sa

revision = "o513914dea14"
down_revision = "n402803cdf13"
branch_labels = depends_on = None


def upgrade():
    with op.batch_alter_table("employees") as batch:
        batch.add_column(sa.Column("external_id", sa.String(100)))
        batch.add_column(sa.Column("email", sa.String(254)))
        batch.create_unique_constraint("uq_employee_external", ["organization_id", "external_id"])
        batch.create_unique_constraint("uq_employee_email", ["organization_id", "email"])
    op.create_table(
        "employee_imports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("rows", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.Float(), nullable=False),
        sa.Column("committed_at", sa.Float()),
        sa.Column("count", sa.Integer(), nullable=False),
    )


def downgrade():
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT count(*) FROM employee_imports")) or bind.scalar(
        sa.text("SELECT count(*) FROM employees WHERE external_id IS NOT NULL OR email IS NOT NULL")
    ):
        raise RuntimeError("Refusing to discard employee/import history; restore a verified backup")
    op.drop_table("employee_imports")
    with op.batch_alter_table("employees") as batch:
        batch.drop_constraint("uq_employee_external", type_="unique")
        batch.drop_constraint("uq_employee_email", type_="unique")
        batch.drop_column("external_id")
        batch.drop_column("email")
