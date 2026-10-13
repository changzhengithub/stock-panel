"""Track snapshot provenance and independently imported free-source history."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "publications",
        sa.Column("source", sa.String(), nullable=False, server_default="Tushare Pro"),
    )
    op.add_column(
        "publications", sa.Column("missing_count", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "publications",
        sa.Column("missing_cap_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "history_bars",
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), primary_key=True),
        sa.Column("trade_date", sa.String(), primary_key=True),
        sa.Column("raw_close", sa.Float(), nullable=False),
        sa.Column("adjusted_close", sa.Float(), nullable=False),
    )
    op.create_table(
        "history_imports",
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), primary_key=True),
        sa.Column("start_date", sa.String(), nullable=False),
        sa.Column("basis_date", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("missing_days", sa.Text(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("updated_at", sa.String(), nullable=False),
    )


def downgrade():
    op.drop_table("history_imports")
    op.drop_table("history_bars")
    for name in ("source", "missing_count", "missing_cap_count"):
        op.drop_column("publications", name)
