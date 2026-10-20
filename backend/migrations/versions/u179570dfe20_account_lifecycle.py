"""Separate platform authority, account audit and explicit organization suspension."""

from alembic import op
import sqlalchemy as sa

revision = "u179570dfe20"
down_revision = "6d8f2a91c043"
branch_labels = depends_on = None


def upgrade():
    # The merge guarantees created_at, suspended and platform_administrators
    # already exist. Their owning migrations also own their eventual removal.
    op.add_column("users", sa.Column("last_login_at", sa.Float(), nullable=True))
    with op.batch_alter_table("organizations") as batch:
        batch.alter_column("suspended", existing_type=sa.Boolean(), server_default=None)
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
    with op.batch_alter_table("organizations") as batch:
        batch.alter_column("suspended", existing_type=sa.Boolean(), server_default=sa.false())
    with op.batch_alter_table("users") as batch:
        batch.drop_column("last_login_at")
