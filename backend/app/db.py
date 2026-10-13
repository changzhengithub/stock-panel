from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from .settings import db_path


def make_engine(path=None):
    path = path or db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{path}", connect_args={"check_same_thread": False, "timeout": 30}
    )

    @event.listens_for(engine, "connect")
    def configure(connection, _):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    return engine


engine = make_engine()
Session = sessionmaker(engine, expire_on_commit=False)


def migrate():
    from alembic import command
    from alembic.config import Config

    from .settings import ROOT

    config = Config(str(ROOT / "backend/alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "backend/migrations"))
    import fcntl

    with db_path().with_suffix(".migrate.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        command.upgrade(config, "head")
