"""Small catalogue projections avoid reading full company evidence on every search."""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("chain_revisions", sa.Column("catalog", sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table("chain_revisions") as table:
        table.drop_column("catalog")
