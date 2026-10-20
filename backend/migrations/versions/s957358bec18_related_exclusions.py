"""Audited exclusions for verified identifier relationships."""

from alembic import op
import sqlalchemy as sa

revision = "s957358bec18"
down_revision = "r846247adb17"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "related_exclusions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("left_call_id", sa.String(36), sa.ForeignKey("calls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("right_call_id", sa.String(36), sa.ForeignKey("calls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.UniqueConstraint("organization_id", "left_call_id", "right_call_id", name="uq_related_exclusion"),
    )
    for name in ["organization_id", "left_call_id", "right_call_id"]:
        op.create_index("ix_related_exclusions_" + name, "related_exclusions", [name])


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM related_exclusions")):
        raise RuntimeError("Cannot discard relationship exclusions. Restore a verified backup.")
    op.drop_table("related_exclusions")
