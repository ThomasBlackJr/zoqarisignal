"""Structured tenant-owned attributes and append-only correction provenance."""

from alembic import op
import sqlalchemy as sa

revision = "r846247adb17"
down_revision = "9c2a7e6b410f"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "call_attributes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("call_id", sa.String(36), sa.ForeignKey("calls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("value", sa.String(500)),
        sa.Column("normalized_value", sa.String(500)),
        sa.Column("confidence", sa.Float()),
        sa.Column("source_start", sa.Integer()),
        sa.Column("source_end", sa.Integer()),
        sa.Column("source_segment", sa.Integer()),
        sa.Column("timestamp", sa.Float()),
        sa.Column("source_fingerprint", sa.String(64)),
        sa.Column("origin", sa.String(20), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
        sa.UniqueConstraint("organization_id", "call_id", "key", name="uq_call_attribute"),
    )
    op.create_index("ix_attribute_lookup", "call_attributes", ["organization_id", "key", "normalized_value"])
    for name in ["organization_id", "call_id"]:
        op.create_index("ix_call_attributes_" + name, "call_attributes", [name])
    op.create_table(
        "attribute_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("call_id", sa.String(36), sa.ForeignKey("calls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("previous", sa.JSON()),
        sa.Column("current", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
    )
    for name in ["organization_id", "call_id"]:
        op.create_index("ix_attribute_events_" + name, "attribute_events", [name])


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM attribute_events")):
        raise RuntimeError("Cannot discard attribute correction history. Restore a verified backup.")
    op.drop_table("attribute_events")
    op.drop_table("call_attributes")
