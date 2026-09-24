"""Nullable reporting and account links; preserve all original records."""

from alembic import op
import sqlalchemy as sa

revision = "i957358dfa08"
down_revision = "h846247cef07"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("employees") as batch:
        batch.add_column(sa.Column("manager_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("linked_user_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_employee_manager", "employees", ["manager_id"], ["id"])
        batch.create_foreign_key("fk_employee_user", "users", ["linked_user_id"], ["id"])
        batch.create_index("ix_employees_manager_id", ["manager_id"])
        batch.create_unique_constraint("uq_employee_linked_user", ["linked_user_id"])
    op.create_table(
        "employee_hierarchy_changes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("employee_id", sa.String(36), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("previous_manager_id", sa.String(36), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("manager_id", sa.String(36), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("previous_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("changed_at", sa.Float(), nullable=False),
    )
    op.create_index("ix_employee_hierarchy_changes_employee_id", "employee_hierarchy_changes", ["employee_id"])


def downgrade():
    bind = op.get_bind()
    if (
        bind.execute(sa.text("SELECT count(*) FROM employee_hierarchy_changes")).scalar()
        or bind.execute(
            sa.text("SELECT count(*) FROM employees WHERE manager_id IS NOT NULL OR linked_user_id IS NOT NULL")
        ).scalar()
    ):
        raise RuntimeError("Hierarchy or link history exists; restore a verified backup instead")
    op.drop_table("employee_hierarchy_changes")
    with op.batch_alter_table("employees") as batch:
        batch.drop_constraint("fk_employee_manager", type_="foreignkey")
        batch.drop_constraint("fk_employee_user", type_="foreignkey")
        batch.drop_constraint("uq_employee_linked_user", type_="unique")
        batch.drop_index("ix_employees_manager_id")
        batch.drop_column("manager_id")
        batch.drop_column("linked_user_id")
