"""Optional entitlement expiry and operator audit reason; no access grants or data rewrites."""

from alembic import op
import sqlalchemy as sa

revision = "t068469cfd19"
down_revision = "s957358bec18"
branch_labels = depends_on = None


def upgrade():
    with op.batch_alter_table("entitlement_events") as batch:
        batch.alter_column("expires_at", existing_type=sa.Float(), nullable=True)
        batch.add_column(sa.Column("reason", sa.String(500), nullable=True))


def downgrade():
    if op.get_bind().scalar(
        sa.text("SELECT count(*) FROM entitlement_events WHERE reason IS NOT NULL OR expires_at IS NULL")
    ):
        raise RuntimeError("Pilot audit history exists. Restore a verified backup rather than discard it.")
    with op.batch_alter_table("entitlement_events") as batch:
        batch.drop_column("reason")
        batch.alter_column("expires_at", existing_type=sa.Float(), nullable=False)
