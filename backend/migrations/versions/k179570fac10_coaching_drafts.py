"""Persist bounded coaching choices; no changes to existing records or preferences."""

from alembic import op
import sqlalchemy as sa

revision = "k179570fac10"
down_revision = "j068469efb09"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "coaching_drafts",
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), primary_key=True),
        sa.Column("issue_id", sa.String(64), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("choice", sa.JSON(), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
    )


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM coaching_drafts")):
        raise RuntimeError("Refusing to discard saved coaching choices; restore a verified backup.")
    op.drop_table("coaching_drafts")
