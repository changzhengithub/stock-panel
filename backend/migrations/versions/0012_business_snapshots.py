"""Source snapshots and resumable full-universe collection audit."""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "business_snapshots",
        sa.Column("ts_code", sa.String(), primary_key=True),
        sa.Column("content_hash", sa.String(), primary_key=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("collected_at", sa.String(), nullable=False),
    )
    op.create_index("ix_business_snapshots_collected_at", "business_snapshots", ["collected_at"])
    op.create_table(
        "business_collections",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("started_at", sa.String(), nullable=False),
        sa.Column("finished_at", sa.String()),
        sa.Column("payload", sa.JSON(), nullable=False),
    )


def downgrade():
    op.drop_table("business_collections")
    op.drop_table("business_snapshots")
