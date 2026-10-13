"""Store actual daily OHLC values for candlestick charts."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    for column in ("open", "high", "low"):
        op.add_column("daily_quotes", sa.Column(column, sa.Float(), nullable=True))
    for column in ("adjusted_open", "adjusted_high", "adjusted_low"):
        op.add_column("history_bars", sa.Column(column, sa.Float(), nullable=True))


def downgrade():
    for column in ("adjusted_low", "adjusted_high", "adjusted_open"):
        op.drop_column("history_bars", column)
    for column in ("low", "high", "open"):
        op.drop_column("daily_quotes", column)
