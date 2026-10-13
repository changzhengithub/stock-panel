"""Store unadjusted daily trading volume in hands."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("daily_quotes", sa.Column("volume", sa.Float(), nullable=True))
    op.add_column("history_bars", sa.Column("volume", sa.Float(), nullable=True))


def downgrade():
    op.drop_column("history_bars", "volume")
    op.drop_column("daily_quotes", "volume")
