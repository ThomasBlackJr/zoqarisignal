"""Add nullable derived conversation cache without changing raw transcripts."""

from alembic import op
import sqlalchemy as sa

revision = "b192cb82ae01"
down_revision = "a2623e115e90"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("transcripts", sa.Column("conversation", sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table("transcripts") as batch_op:
        batch_op.drop_column("conversation")
