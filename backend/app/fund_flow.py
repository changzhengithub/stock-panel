"""Bounded, independent fund collection and atomic source-scoped publication."""

import fcntl
import hashlib
import json
import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db import Session
from app.models import FundBoard, FundCache, FundDaily, FundRun, utcnow
from app.providers.fund_flow import PERIODS, SOURCE, TZ, FundFlowProvider
from app.providers.tushare import ProviderError

log = logging.getLogger(__name__)


def board_id(kind, code):
    return f"EM-{kind}-{code}"


def scope(kind, period, code=None, dataset="ranks"):
    return f"{kind}:{code or 'all'}:{dataset}:{period}"


def read(session, key):
    cache = session.get(FundCache, key)
    if not cache:
        return None
    return {**json.loads(cache.payload), "batch_id": cache.batch_id, "fetched_at": cache.fetched_at}


def publish(sessions, key, kind, data, code=None, dataset="ranks"):
    fetched = utcnow()
    # Version is based on semantic data. Refreshing identical data doesn't redraw charts.
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, allow_nan=False)
    version = hashlib.sha256(payload.encode()).hexdigest()[:20]
    with sessions.begin() as session:
        old = read(session, key)
        if old and len(data["rows"]) < len(old["rows"]) * 0.8 and dataset != "history":
            raise ProviderError("资金目录/成分数量异常缩减，保留上一批数据")
        if dataset == "ranks":
            for row in data["rows"]:
                identity = board_id(kind, row["code"])
                board = session.get(FundBoard, identity)
                if not board:
                    board = FundBoard(
                        id=identity, source=SOURCE, kind=kind, code=row["code"], name=row["name"]
                    )
                    session.add(board)
                board.name = row["name"]
        if dataset == "history":
            identity = board_id(kind, code)
            if session.get(FundBoard, identity) is None:
                raise ProviderError("资金板块尚未注册")
            for row in data["rows"]:
                if row.get("provisional"):
                    continue
                daily = session.get(FundDaily, (identity, row["trade_date"]))
                if not daily:
                    daily = FundDaily(board_id=identity, trade_date=row["trade_date"])
                    session.add(daily)
                daily.payload, daily.fetched_at = json.dumps(row), fetched
            session.flush()
            # Retain older imported days when the upstream's rolling window contracts.
            persisted = [
                json.loads(r.payload)
                for r in session.scalars(select(FundDaily).where(FundDaily.board_id == identity))
            ]
            provisional = [r for r in data["rows"] if r.get("provisional")]
            data = {**data, "rows": sorted(persisted + provisional, key=lambda r: r["trade_date"])}
            payload = json.dumps(data, ensure_ascii=False, sort_keys=True, allow_nan=False)
            version = hashlib.sha256(payload.encode()).hexdigest()[:20]
        cache = session.get(FundCache, key)
        if not cache:
            cache = FundCache(key=key)
            session.add(cache)
        cache.payload, cache.batch_id, cache.fetched_at = payload, version, fetched
    return version


def collect(
    kind="concept",
    period="today",
    code=None,
    dataset="ranks",
    sessions=Session,
    provider_factory=FundFlowProvider,
    force=False,
):
    key = scope(kind, period, code, dataset)
    with sessions() as session:
        path = Path(session.get_bind().url.database)
        run = session.get(FundRun, key)
        if not force and run and run.retry_at and run.retry_at > utcnow():
            return {"scope": key, "skipped": "backoff", "error": run.error}
    lock = path.with_name(
        path.name + ".fund-" + hashlib.sha256(key.encode()).hexdigest()[:16] + ".lock"
    )
    with lock.open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"scope": key, "skipped": "running"}
        try:
            with sessions.begin() as session:
                run = session.get(FundRun, key)
                if not run:
                    run = FundRun(key=key)
                    session.add(run)
                run.started_at, run.finished_at, run.error, run.retry_at = (
                    utcnow(),
                    None,
                    None,
                    None,
                )
            provider = provider_factory()
            try:
                data = (
                    provider.history(code)
                    if dataset == "history"
                    else provider.listing(kind, period, code)
                )
            finally:
                provider.close()
            version = publish(sessions, key, kind, data, code, dataset)
            with sessions.begin() as session:
                run = session.get(FundRun, key)
                run.finished_at = utcnow()
            return {
                "scope": key,
                "batch_id": version,
                "rows": len(data["rows"]),
                "trade_date": data["trade_date"],
            }
        except Exception as exc:
            # Only provider validation messages are user-facing; unexpected errors are redacted.
            error = (
                str(exc)
                if isinstance(exc, ProviderError)
                else f"资金任务失败（{type(exc).__name__}）"
            )
            with sessions.begin() as session:
                run = session.get(FundRun, key)
                run.finished_at, run.error = utcnow(), error
                run.retry_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
            return {"scope": key, "error": error}
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def enabled():
    return os.getenv("FUND_FLOW_ENABLED", "1") != "0"


_dispatch_lock = threading.Lock()
_active = set()


def refresh_pending(session, key):
    with _dispatch_lock:
        return (str(session.get_bind().url), key) in _active


def request_refresh(session, kind, period, code=None, dataset="ranks"):
    """GET returns immediately; deduplicate by database and dataset, including processes."""
    if not enabled():
        return
    key = scope(kind, period, code, dataset)
    data = read(session, key)
    run = session.get(FundRun, key)
    now = datetime.now(timezone.utc)
    ttl = 300 if dataset != "history" else 1800
    if data and (now - datetime.fromisoformat(data["fetched_at"])).total_seconds() < ttl:
        return
    if run and run.retry_at and run.retry_at > now.isoformat():
        return
    identity = (str(session.get_bind().url), key)
    with _dispatch_lock:
        if identity in _active or len(_active) >= 3:
            return
        _active.add(identity)
    factory = sessionmaker(session.get_bind(), expire_on_commit=False)

    def work():
        try:
            collect(kind, period, code, dataset, sessions=factory)
        finally:
            with _dispatch_lock:
                _active.discard(identity)

    threading.Thread(target=work, name="fund-flow-demand", daemon=True).start()


def start_worker():
    stop = threading.Event()
    if not enabled():
        return stop

    def work():
        while not stop.is_set():
            try:
                with Session() as session:
                    from app.realtime import expected_date

                    now = datetime.now(TZ)
                    day = expected_date(session, now)
                    trading = day == now.strftime("%Y%m%d")
                    # Run startup catch-up; subsequent scopes use their own TTL/backoff.
                    for kind in ("concept", "industry"):
                        for period in PERIODS:
                            if stop.is_set():
                                return
                            data = read(session, scope(kind, period))
                            if (
                                not data
                                or trading
                                and "091500" <= now.strftime("%H%M%S") <= "163000"
                                or (day is not None and data["trade_date"] < day)
                            ):
                                request_refresh(session, kind, period)
            except Exception:
                log.exception("资金任务调度失败，行情任务继续运行")
            stop.wait(60)

    threading.Thread(target=work, name="fund-flow-scheduler", daemon=True).start()
    return stop
