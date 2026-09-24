"""Scoped invitations and per-user preferences."""

from alembic import op
import sqlalchemy as sa

revision = "h846247cef07"
down_revision = "g735136bdf06"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "invitations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("invited_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("expires_at", sa.Float(), nullable=False),
        sa.Column("accepted_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("accepted_at", sa.Float(), nullable=True),
    )
    op.create_index("ix_invitations_organization_id", "invitations", ["organization_id"])
    op.create_table(
        "user_preferences",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("appearance", sa.String(10), nullable=False),
        sa.Column("modules", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
    )


def downgrade():
    bind = op.get_bind()
    if (
        bind.execute(sa.text("SELECT count(*) FROM invitations")).scalar()
        or bind.execute(sa.text("SELECT count(*) FROM user_preferences")).scalar()
    ):
        raise RuntimeError("Team invitations or personal preferences exist; restore a backup instead")
    op.drop_table("user_preferences")
    op.drop_table("invitations")
