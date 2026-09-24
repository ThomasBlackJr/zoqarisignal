"""Explicit managers, multiple published scorecards and administrative deletion audit."""

from alembic import op
import sqlalchemy as sa

revision = "j068469efb09"
down_revision = "i957358dfa08"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("employees", sa.Column("manager_eligible", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute(
        "UPDATE employees SET manager_eligible = true WHERE id IN (SELECT manager_id FROM employees WHERE manager_id IS NOT NULL)"
    )
    op.drop_index("one_active_rubric", table_name="rubrics")
    with op.batch_alter_table("upload_batches") as batch:
        batch.add_column(sa.Column("rubric_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_batch_rubric", "rubrics", ["rubric_id"], ["id"])
    op.create_table(
        "admin_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("resource_type", sa.String(20), nullable=False),
        sa.Column("resource_id", sa.String(36), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
    )
    op.create_index("ix_admin_events_organization_id", "admin_events", ["organization_id"])
    op.create_index("ix_admin_events_resource_id", "admin_events", ["resource_id"])
    op.create_table(
        "pending_audio_deletions",
        sa.Column("call_id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("storage_name", sa.String(50), nullable=False),
        sa.Column("event_id", sa.String(36), sa.ForeignKey("admin_events.id"), nullable=False),
    )
    op.create_index("ix_pending_audio_deletions_organization_id", "pending_audio_deletions", ["organization_id"])


def downgrade():
    bind = op.get_bind()
    checks = [
        "SELECT count(*) FROM admin_events",
        "SELECT count(*) FROM pending_audio_deletions",
        "SELECT count(*) FROM employees WHERE manager_eligible = true",
        "SELECT count(*) FROM upload_batches WHERE rubric_id IS NOT NULL",
        "SELECT count(*) FROM (SELECT organization_id FROM rubrics WHERE status = 'ACTIVE' GROUP BY organization_id HAVING count(*) > 1) AS multiple",
    ]
    if any(bind.execute(sa.text(query)).scalar() for query in checks):
        raise RuntimeError("Product-control state exists; restore a verified backup for rollback.")
    op.drop_table("pending_audio_deletions")
    op.drop_table("admin_events")
    with op.batch_alter_table("upload_batches") as batch:
        batch.drop_constraint("fk_batch_rubric", type_="foreignkey")
        batch.drop_column("rubric_id")
    with op.batch_alter_table("employees") as batch:
        batch.drop_column("manager_eligible")
    op.create_index(
        "one_active_rubric",
        "rubrics",
        ["organization_id", "status"],
        unique=True,
        sqlite_where=sa.text("status = 'ACTIVE'"),
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
