"""Short-lived salted verification codes; existing reset/invitation tokens unchanged."""

from alembic import op
import sqlalchemy as sa

revision = "m391792bce12"
down_revision = "l280681abd11"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "verification_codes",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("challenge_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.Float(), nullable=False),
        sa.Column("sent_at", sa.Float(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
    )


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM verification_codes")):
        raise RuntimeError("Refusing to discard verification challenges. Restore a verified backup.")
    op.drop_table("verification_codes")
