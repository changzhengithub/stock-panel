from alembic import context
from app.db import engine
from app.models import Base
import app.business_models  # noqa: F401
import app.chain_models  # noqa: F401 - register chain metadata for migrations

with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()
