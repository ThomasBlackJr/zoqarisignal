"""Stable audit references and immutable deterministic flagged-term evidence."""

from alembic import op
import sqlalchemy as sa

revision = "l280681abd11"
down_revision = "k179570fac10"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "audit_sequence", sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True), sqlite_autoincrement=True
    )
    with op.batch_alter_table("calls") as batch:
        batch.add_column(sa.Column("audit_number", sa.String(30), nullable=True))
        batch.create_index("ix_calls_audit_number", ["audit_number"], unique=True)
    bind = op.get_bind()
    for cid in bind.execute(sa.text("SELECT id FROM calls ORDER BY created_at, id")).scalars().all():
        seq = bind.execute(sa.text("INSERT INTO audit_sequence DEFAULT VALUES RETURNING id")).scalar_one()
        bind.execute(sa.text("UPDATE calls SET audit_number=:ref WHERE id=:id"), {"ref": f"SIG-{seq:08d}", "id": cid})
    op.create_table(
        "flag_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("phrase", sa.String(200), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("notify", sa.Boolean(), nullable=False),
        sa.Column("recipients", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
    )
    op.create_index("ix_flag_rules_organization_id", "flag_rules", ["organization_id"])
    op.create_table(
        "flag_detections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("call_id", sa.String(36), sa.ForeignKey("calls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_id", sa.String(36), sa.ForeignKey("flag_rules.id"), nullable=False),
        sa.Column("rule_revision", sa.Integer(), nullable=False),
        sa.Column("transcript_revision", sa.Integer(), nullable=False),
        sa.Column("source_fingerprint", sa.String(64), nullable=False),
        sa.Column("phrase", sa.String(200), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("matches", sa.JSON(), nullable=False),
        sa.Column("match_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.UniqueConstraint("call_id", "rule_id", "rule_revision", "transcript_revision", name="uq_flag_detection"),
    )
    op.create_index("ix_flag_detections_call_id", "flag_detections", ["call_id"])
    op.create_table(
        "flag_notifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "detection_id", sa.String(36), sa.ForeignKey("flag_detections.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("recipient_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("attempted_at", sa.Float(), nullable=True),
        sa.UniqueConstraint("detection_id", "recipient_id", name="uq_flag_recipient"),
    )
    op.create_index("ix_flag_notifications_detection_id", "flag_notifications", ["detection_id"])


def downgrade():
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT count(*) FROM audit_sequence")) or bind.scalar(
        sa.text("SELECT count(*) FROM flag_rules")
    ):
        raise RuntimeError("Refusing to discard audit references or flagged-term history. Restore a verified backup.")
    op.drop_table("flag_notifications")
    op.drop_table("flag_detections")
    op.drop_table("flag_rules")
    with op.batch_alter_table("calls") as batch:
        batch.drop_index("ix_calls_audit_number")
        batch.drop_column("audit_number")
    op.drop_table("audit_sequence")
