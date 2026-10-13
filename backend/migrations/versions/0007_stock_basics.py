"""Store dated valuation, turnover and share-capital snapshot fields."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    for column in (
        "float_market_cap", "turnover_rate", "pe_ratio", "pb_ratio",
        "total_shares", "float_shares",
    ):
        op.add_column("daily_quotes", sa.Column(column, sa.Float(), nullable=True))
    op.add_column("daily_quotes", sa.Column("pe_basis", sa.String(), nullable=True))


def downgrade():
    op.drop_column("daily_quotes", "pe_basis")
    for column in (
        "float_shares", "total_shares", "pb_ratio", "pe_ratio",
        "turnover_rate", "float_market_cap",
    ):
        op.drop_column("daily_quotes", column)
