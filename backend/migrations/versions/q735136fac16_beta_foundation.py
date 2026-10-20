"""Independent beta grants, organization suspension and separate platform authority."""

from alembic import op
import sqlalchemy as sa

revision = "q735136fac16"
down_revision = "p624025efb15"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("organizations", sa.Column("suspended", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("invitations", sa.Column("platform_issued", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "beta_access",
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), primary_key=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("expires_at", sa.Float(), nullable=True),
    )
    op.create_table(
        "platform_administrators",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("active", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "platform_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.Float(), nullable=False),
    )
    op.create_index("ix_platform_events_actor_id", "platform_events", ["actor_id"])
    op.create_index("ix_platform_events_organization_id", "platform_events", ["organization_id"])


def downgrade():
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT count(*) FROM invitations WHERE platform_issued = true")):
        raise RuntimeError("Platform invitation history exists. Restore a verified backup.")
    for table in ("platform_events", "platform_administrators", "beta_access"):
        if bind.scalar(sa.text(f"SELECT count(*) FROM {table}")):
            raise RuntimeError("Beta/platform history exists. Restore a verified backup rather than discard it.")
    if bind.scalar(sa.text("SELECT count(*) FROM organizations WHERE suspended = true")):
        raise RuntimeError("Suspension state exists. Restore a verified backup rather than discard it.")
    op.drop_table("platform_events")
    op.drop_table("platform_administrators")
    op.drop_table("beta_access")
    with op.batch_alter_table("invitations") as batch:
        batch.drop_column("platform_issued")
    with op.batch_alter_table("organizations") as batch:
        batch.drop_column("suspended")
