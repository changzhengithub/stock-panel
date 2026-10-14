"""Durable scheduled industry analysis update audit."""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "chain_update_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("started_at", sa.String(), nullable=False),
        sa.Column("finished_at", sa.String(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_chain_update_runs_started_at", "chain_update_runs", ["started_at"])


def downgrade():
    op.drop_table("chain_update_runs")
