"""Persisted batch ingestion reuses normal interactions."""

from alembic import op
import sqlalchemy as sa

revision = "f624025ace05"
down_revision = "e513f149bd04"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("calls", sa.Column("content_sha256", sa.String(64), nullable=True))
    op.create_index("ix_calls_content_sha256", "calls", ["content_sha256"])
    op.create_table(
        "upload_batches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("request_key", sa.String(64), nullable=False),
        sa.Column("manifest_hash", sa.String(64), nullable=False),
        sa.UniqueConstraint("organization_id", "request_key", name="uq_batch_request"),
    )
    op.create_index("ix_upload_batches_organization_id", "upload_batches", ["organization_id"])
    op.create_table(
        "upload_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("batch_id", sa.String(36), sa.ForeignKey("upload_batches.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.Float(), nullable=False),
        sa.Column("call_id", sa.String(36), sa.ForeignKey("calls.id"), nullable=True),
        sa.Column("duplicate", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_upload_items_batch_id", "upload_items", ["batch_id"])
    op.create_index("ix_upload_items_call_id", "upload_items", ["call_id"])


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM upload_batches")).scalar():
        raise RuntimeError("Batch history exists; restore a backup rather than discard it")
    op.drop_table("upload_items")
    op.drop_table("upload_batches")
    op.drop_index("ix_calls_content_sha256", table_name="calls")
    op.drop_column("calls", "content_sha256")
