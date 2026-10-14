"""Source-scoped fund boards, atomic caches, historical days and task status."""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "fund_boards",
        sa.Column("id", sa.String(), primary_key=True),
        *[sa.Column(k, sa.String(), nullable=False) for k in ("source", "kind", "code", "name")],
    )
    op.create_table(
        "fund_caches",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("batch_id", sa.String(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.String(), nullable=False),
    )
    op.create_table(
        "fund_daily",
        sa.Column("board_id", sa.String(), sa.ForeignKey("fund_boards.id"), primary_key=True),
        sa.Column("trade_date", sa.String(), primary_key=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.String(), nullable=False),
    )
    op.create_table(
        "fund_runs",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("started_at", sa.String(), nullable=False),
        *[sa.Column(k, sa.Text(), nullable=True) for k in ("finished_at", "error", "retry_at")],
    )


def downgrade():
    for table in ("fund_daily", "fund_runs", "fund_caches", "fund_boards"):
        op.drop_table(table)
