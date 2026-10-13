"""Keep the existing first-level classification and add verified second-level assignments."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("industries", sa.Column("level", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("industries", sa.Column("parent_id", sa.String(), nullable=True))
    op.add_column(
        "stocks",
        # SQLite cannot add a foreign-key constraint in place. The sync validates
        # the category IDs before writing, keeping this migration additive.
        sa.Column("industry_l2_id", sa.String(), nullable=True),
    )
    op.create_index("ix_stocks_industry_l2_id", "stocks", ["industry_l2_id"])
    op.create_table(
        "industry_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("fetched_at", sa.String(), nullable=False),
        sa.Column("source_updated_at", sa.String(), nullable=True),
        sa.Column("classified_count", sa.Integer(), nullable=False),
        sa.Column("stock_count", sa.Integer(), nullable=False),
    )


def downgrade():
    op.drop_table("industry_snapshots")
    op.drop_index("ix_stocks_industry_l2_id", table_name="stocks")
    with op.batch_alter_table("stocks") as batch:
        batch.drop_column("industry_l2_id")
    op.drop_column("industries", "parent_id")
    op.drop_column("industries", "level")
