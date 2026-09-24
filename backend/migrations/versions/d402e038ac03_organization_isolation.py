"""Organization ownership; migrate all existing records into one legacy workspace."""

from alembic import op
import sqlalchemy as sa

revision = "d402e038ac03"
down_revision = "c301d927fb02"
branch_labels = None
depends_on = None
LEGACY_ORG = "00000000-0000-0000-0000-000000000002"


def upgrade():
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
    )
    op.get_bind().execute(
        sa.text("INSERT INTO organizations (id,name,created_at) VALUES (:id,'Signal workspace',0)"), {"id": LEGACY_ORG}
    )
    for table in ("users", "calls", "rubrics"):
        op.add_column(table, sa.Column("organization_id", sa.String(36), nullable=True))
        op.get_bind().execute(sa.text(f"UPDATE {table} SET organization_id=:id"), {"id": LEGACY_ORG})
        with op.batch_alter_table(table) as batch:
            batch.alter_column("organization_id", existing_type=sa.String(36), nullable=False)
            batch.create_foreign_key(f"fk_{table}_organization", "organizations", ["organization_id"], ["id"])
            batch.create_index(f"ix_{table}_organization_id", ["organization_id"])
    with op.batch_alter_table("rubrics", naming_convention={"uq": "uq_%(table_name)s_%(column_0_name)s"}) as batch:
        batch.drop_constraint("uq_rubrics_version", type_="unique")
        batch.create_unique_constraint("uq_rubric_org_version", ["organization_id", "version"])
    op.drop_index("one_active_rubric", table_name="rubrics")
    op.create_index(
        "one_active_rubric",
        "rubrics",
        ["organization_id", "status"],
        unique=True,
        sqlite_where=sa.text("status = 'ACTIVE'"),
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM organizations")).scalar() > 1:
        raise RuntimeError("Cannot remove tenant isolation from multiple organizations; restore a backup instead")
    op.drop_index("one_active_rubric", table_name="rubrics")
    with op.batch_alter_table("rubrics") as batch:
        batch.drop_constraint("uq_rubric_org_version", type_="unique")
        batch.create_unique_constraint("uq_rubrics_version", ["version"])
    for table in ("users", "calls", "rubrics"):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f"fk_{table}_organization", type_="foreignkey")
            batch.drop_index(f"ix_{table}_organization_id")
            batch.drop_column("organization_id")
    op.create_index(
        "one_active_rubric",
        "rubrics",
        ["status"],
        unique=True,
        sqlite_where=sa.text("status = 'ACTIVE'"),
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.drop_table("organizations")
