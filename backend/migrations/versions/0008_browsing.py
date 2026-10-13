"""Preserve raw candles and dated index information."""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("raw_open", "raw_high", "raw_low"):
        op.add_column("history_bars", sa.Column(name, sa.Float(), nullable=True))
    for table in ("industry_representatives", "industry_representatives_l2"):
        op.add_column(table, sa.Column("weight_date", sa.String(), nullable=True))
    op.create_table(
        "industry_index_quotes",
        sa.Column("industry_id", sa.String(), sa.ForeignKey("industries.id"), primary_key=True),
        sa.Column("trade_date", sa.String(), primary_key=True),
        sa.Column("close", sa.Float()),
        sa.Column("pct_chg", sa.Float()),
        sa.Column("error", sa.String()),
        sa.Column("fetched_at", sa.String(), nullable=False),
    )


def downgrade():
    op.drop_table("industry_index_quotes")
    for table in ("industry_representatives", "industry_representatives_l2"):
        op.drop_column(table, "weight_date")
    for name in ("raw_open", "raw_high", "raw_low"):
        op.drop_column("history_bars", name)
