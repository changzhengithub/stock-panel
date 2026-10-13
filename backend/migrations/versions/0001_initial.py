"""Initial v1 schema. Future model changes require a new migration."""

import importlib.util
from pathlib import Path

from alembic import op

spec = importlib.util.spec_from_file_location(
    "schema_v1", Path(__file__).parents[1] / "schema_v1.py"
)
schema = importlib.util.module_from_spec(spec)
spec.loader.exec_module(schema)
Base = schema.Base
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    Base.metadata.create_all(op.get_bind())


def downgrade():
    Base.metadata.drop_all(op.get_bind())
