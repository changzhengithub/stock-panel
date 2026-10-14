"""Local maintenance only. No network or unattended review on application startup."""

import fcntl
import json
from contextlib import contextmanager
from pathlib import Path
from threading import local

from app.chain_service import import_content, publish_content, review_content, validate_content
from app.settings import db_path

_locks = local()


@contextmanager
def chain_lock():
    # The scheduled pipeline holds one lock across collection, build and publication.
    if getattr(_locks, "depth", 0):
        _locks.depth += 1
        try:
            yield
        finally:
            _locks.depth -= 1
        return
    p = db_path().with_suffix(".chains.lock")
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _locks.depth = 1
        try:
            yield
        finally:
            _locks.depth = 0
            fcntl.flock(f, fcntl.LOCK_UN)


def maintain(command, factory, path=None, revision=None, reviewer=None, note=None):
    with chain_lock():
        if command in ("validate-chain", "import-chain"):
            if not path:
                raise ValueError("请通过 --chain-file 指定内容包")
            value = json.loads(Path(path).read_text())
            if command == "validate-chain":
                doc = validate_content(value)
                return dict(
                    ok=True,
                    chain_id=doc["id"],
                    nodes=len(doc["nodes"]),
                    edges=len(doc["edges"]),
                    stocks=len(doc["stocks"]),
                    sources=len(doc["sources"]),
                )
            return import_content(factory, value)
        if command == "review-chain":
            return review_content(factory, revision, reviewer or "", note or "")
        if command == "publish-chain":
            return publish_content(factory, revision)
        from sqlalchemy import select

        from app.chain_models import ChainImportRun, ChainRevision, IndustryChain

        with factory() as s:
            chains = list(s.scalars(select(IndustryChain)))
            return {
                "chains": [
                    {
                        "id": x.id,
                        "revision_id": x.published_revision,
                        "state": s.get(ChainRevision, x.published_revision).state
                        if x.published_revision
                        else "未发布",
                    }
                    for x in chains
                ],
                "failed_imports": [
                    {"chain_id": x.chain_id, "error": x.error}
                    for x in s.scalars(
                        select(ChainImportRun).where(ChainImportRun.state == "failed")
                    )
                ],
            }
