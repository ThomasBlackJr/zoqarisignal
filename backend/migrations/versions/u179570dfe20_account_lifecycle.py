"""Separate platform authority, account audit and explicit organization suspension."""

from alembic import op
import sqlalchemy as sa

revision = "u179570dfe20"
down_revision = "t068469cfd19"
branch_labels = depends_on = None


def upgrade():
    op.add_column("users", sa.Column("created_at", sa.Float(), nullable=True))
    op.add_column("users", sa.Column("last_login_at", sa.Float(), nullable=True))
    op.add_column("organizations", sa.Column("suspended", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("organizations") as batch:
        batch.alter_column("suspended", existing_type=sa.Boolean(), server_default=None)
    op.create_table(
        "platform_administrators",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("active", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "account_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.Float(), nullable=False),
    )
    for column in ("user_id", "organization_id"):
        op.create_index("ix_account_events_" + column, "account_events", [column])


def downgrade():
    bind = op.get_bind()
    for query in (
        "SELECT count(*) FROM platform_administrators",
        "SELECT count(*) FROM account_events",
        "SELECT count(*) FROM organizations WHERE suspended = true",
        "SELECT count(*) FROM users WHERE created_at IS NOT NULL OR last_login_at IS NOT NULL",
    ):
        if bind.scalar(sa.text(query)):
            raise RuntimeError("Account lifecycle history exists. Restore a verified backup instead of discarding it.")
    op.drop_table("account_events")
    op.drop_table("platform_administrators")
    with op.batch_alter_table("organizations") as batch:
        batch.drop_column("suspended")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("created_at")
        batch.drop_column("last_login_at")
