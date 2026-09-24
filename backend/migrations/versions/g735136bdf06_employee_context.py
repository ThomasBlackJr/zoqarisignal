"""Employee attribution and immutable corrected-transcript evaluation context."""

from alembic import op
import sqlalchemy as sa

revision = "g735136bdf06"
down_revision = "f624025ace05"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "employees",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
    )
    op.create_index("ix_employees_organization_id", "employees", ["organization_id"])
    with op.batch_alter_table("calls") as batch:
        batch.add_column(sa.Column("employee_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_calls_employee", "employees", ["employee_id"], ["id"])
        batch.create_index("ix_calls_employee_id", ["employee_id"])
        batch.add_column(sa.Column("assignment_revision", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("requested_transcript_context", sa.JSON(), nullable=True))
    with op.batch_alter_table("calls") as batch:
        batch.alter_column("assignment_revision", server_default=None)
    op.add_column("qa_evaluations", sa.Column("transcript_revision", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("qa_evaluations", sa.Column("transcript_context", sa.JSON(), nullable=True))
    with op.batch_alter_table("qa_evaluations") as batch:
        batch.alter_column("transcript_revision", server_default=None)
    op.create_table(
        "employee_assignments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("call_id", sa.String(36), sa.ForeignKey("calls.id"), nullable=False),
        sa.Column("previous_employee_id", sa.String(36), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("employee_id", sa.String(36), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("changed_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("changed_at", sa.Float(), nullable=False),
    )
    op.create_index("ix_employee_assignments_call_id", "employee_assignments", ["call_id"])


def downgrade():
    bind = op.get_bind()
    if (
        bind.execute(sa.text("SELECT count(*) FROM employees")).scalar()
        or bind.execute(sa.text("SELECT count(*) FROM qa_evaluations WHERE transcript_context IS NOT NULL")).scalar()
        or bind.execute(sa.text("SELECT count(*) FROM calls WHERE requested_transcript_context IS NOT NULL")).scalar()
    ):
        raise RuntimeError("Employee or evaluation context exists; restore a backup instead")
    op.drop_table("employee_assignments")
    with op.batch_alter_table("calls") as batch:
        batch.drop_constraint("fk_calls_employee", type_="foreignkey")
        batch.drop_index("ix_calls_employee_id")
        for name in ("employee_id", "assignment_revision", "requested_transcript_context"):
            batch.drop_column(name)
    with op.batch_alter_table("qa_evaluations") as batch:
        batch.drop_column("transcript_revision")
        batch.drop_column("transcript_context")
    op.drop_table("employees")
