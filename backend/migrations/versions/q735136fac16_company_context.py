"""Optional organization vocabulary and lossless company annotations."""

from alembic import op
import sqlalchemy as sa

revision = "q735136fac16"
down_revision = "p624025efb15"
branch_labels = depends_on = None


def upgrade():
    op.add_column("organizations", sa.Column("transcription_vocabulary", sa.JSON(), nullable=True))
    op.add_column("transcripts", sa.Column("company_corrections", sa.JSON(), nullable=True))


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM organizations WHERE transcription_vocabulary IS NOT NULL")):
        raise RuntimeError("Cannot discard organization vocabulary; restore a verified backup.")
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM transcripts WHERE company_corrections IS NOT NULL")):
        raise RuntimeError("Cannot discard transcription provenance; restore a verified backup.")
    with op.batch_alter_table("transcripts") as batch:
        batch.drop_column("company_corrections")
    with op.batch_alter_table("organizations") as batch:
        batch.drop_column("transcription_vocabulary")
