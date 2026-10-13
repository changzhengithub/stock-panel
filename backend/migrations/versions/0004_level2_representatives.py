"""Store separate second-level industry representative samples."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "industry_representatives_l2",
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), primary_key=True),
        sa.Column("industry_id", sa.String(), sa.ForeignKey("industries.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("reviewed_at", sa.String(), nullable=False),
    )
    op.create_index(
        "ix_industry_representatives_l2_industry_id",
        "industry_representatives_l2",
        ["industry_id"],
    )


def downgrade():
    op.drop_index(
        "ix_industry_representatives_l2_industry_id",
        table_name="industry_representatives_l2",
    )
    op.drop_table("industry_representatives_l2")
