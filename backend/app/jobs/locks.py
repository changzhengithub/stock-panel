"""Read-only liveness check for the advisory sync lock."""

import fcntl

from app.settings import db_path


def sync_running():
    path = db_path().with_suffix(".sync.lock")
    if not path.exists():
        return False
    try:
        with path.open("r") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(stream, fcntl.LOCK_UN)
            return False
    except OSError:
        return None
