"""Join parallel account administration and call intelligence before lifecycle.

Both branches must run: lifecycle reuses the shared account/platform schema
introduced by beta foundation and account administration.
"""

revision = "6d8f2a91c043"
down_revision = ("r846247abd17", "t068469cfd19")
branch_labels = depends_on = None


def upgrade():
    pass


def downgrade():
    pass
