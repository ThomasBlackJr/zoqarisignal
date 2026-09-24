"""Persist hosted billing identifiers and verified-event idempotency."""

from alembic import op
import sqlalchemy as sa

revision = "n402803cdf13"
down_revision = "m391792bce12"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "billing_accounts",
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), primary_key=True),
        sa.Column("customer_id", sa.String(100), unique=True),
        sa.Column("subscription_id", sa.String(100), unique=True),
        sa.Column("checkout_id", sa.String(100)),
        sa.Column("checkout_key", sa.String(36)),
        sa.Column("checkout_expires", sa.Float()),
        sa.Column("checkout_plan", sa.String(40)),
        sa.Column("plan", sa.String(30)),
        sa.Column("interval", sa.String(10)),
        sa.Column("trial_used", sa.Boolean(), nullable=False),
        sa.Column("livemode", sa.Boolean(), nullable=False),
        sa.Column("synced_at", sa.Float()),
    )
    op.create_table(
        "billing_events",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
    )


def downgrade():
    for table in ("billing_accounts", "billing_events"):
        if op.get_bind().execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar():
            raise RuntimeError("Refusing to discard billing history; restore a verified backup instead")
    op.drop_table("billing_events")
    op.drop_table("billing_accounts")
