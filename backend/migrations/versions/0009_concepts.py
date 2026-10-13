"""Add source-scoped concept boards and many-to-many stock membership."""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "concepts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("fetched_at", sa.String(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_concepts_name", "concepts", ["name"])
    op.create_table(
        "concept_members",
        sa.Column("concept_id", sa.String(), sa.ForeignKey("concepts.id"), primary_key=True),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), primary_key=True),
    )
    op.create_index("ix_concept_members_stock_id", "concept_members", ["stock_id"])


def downgrade():
    op.drop_table("concept_members")
    op.drop_table("concepts")
