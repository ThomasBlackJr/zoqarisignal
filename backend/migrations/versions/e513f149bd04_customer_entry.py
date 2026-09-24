"""Verified accounts, subscription gate and customer setup; preserve operational records."""

from alembic import op
import sqlalchemy as sa

revision = "e513f149bd04"
down_revision = "d402e038ac03"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch:
        batch.alter_column("organization_id", existing_type=sa.String(36), nullable=True)
        # Previously provisioned accounts were trusted operator-created accounts.
        batch.add_column(sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.true()))
    with op.batch_alter_table("users") as batch:
        batch.alter_column("email_verified", server_default=None)
    with op.batch_alter_table("organizations") as batch:
        batch.add_column(sa.Column("subscription_status", sa.String(20), nullable=False, server_default="inactive"))
        batch.add_column(sa.Column("entitlement_source", sa.String(30), nullable=True))
        batch.add_column(sa.Column("entitlement_expires_at", sa.Float(), nullable=True))
        batch.add_column(sa.Column("onboarding_completed", sa.Boolean(), nullable=False, server_default=sa.true()))
    with op.batch_alter_table("organizations") as batch:
        batch.alter_column("subscription_status", server_default=None)
        batch.alter_column("onboarding_completed", server_default=None)
    op.create_table(
        "account_tokens",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("expires_at", sa.Float(), nullable=False),
    )
    op.create_index("ix_account_tokens_user_id", "account_tokens", ["user_id"])
    op.create_index("ix_account_tokens_expires_at", "account_tokens", ["expires_at"])
    op.create_table(
        "entitlement_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("expires_at", sa.Float(), nullable=False),
    )
    op.create_index("ix_entitlement_events_organization_id", "entitlement_events", ["organization_id"])


def downgrade():
    bind = op.get_bind()
    if (
        bind.execute(sa.text("SELECT count(*) FROM users WHERE organization_id IS NULL OR email_verified = 0")).scalar()
        or bind.execute(sa.text("SELECT count(*) FROM entitlement_events")).scalar()
        or bind.execute(sa.text("SELECT count(*) FROM account_tokens")).scalar()
        or bind.execute(
            sa.text(
                "SELECT count(*) FROM organizations WHERE subscription_status != 'inactive' OR entitlement_source IS NOT NULL OR entitlement_expires_at IS NOT NULL OR onboarding_completed = 0"
            )
        ).scalar()
    ):
        raise RuntimeError("Customer account/access data exists; restore a backup instead of discarding it")
    op.drop_table("entitlement_events")
    op.drop_table("account_tokens")
    with op.batch_alter_table("organizations") as batch:
        for name in ("subscription_status", "entitlement_source", "entitlement_expires_at", "onboarding_completed"):
            batch.drop_column(name)
    with op.batch_alter_table("users") as batch:
        batch.drop_column("email_verified")
        batch.alter_column("organization_id", existing_type=sa.String(36), nullable=False)
