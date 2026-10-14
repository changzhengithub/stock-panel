"""Free current-market cache, independent of published daily bars and adjustment bases."""

import fcntl
import json
import logging
import os
import threading
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

from sqlalchemy import func, select

from app.db import Session
from app.models import Calendar, Publication, Stock
from app.providers.free import TZ, FreeProvider, date_text, numeric, positive
from app.providers.tushare import ProviderError

log = logging.getLogger(__name__)
FIELDS = (
    "close",
    "pre_close",
    "open",
    "high",
    "low",
    "volume",
    "pct_chg",
    "amount",
    "market_cap",
    "float_market_cap",
    "turnover_rate",
    "pe_ratio",
    "pb_ratio",
    "total_shares",
    "float_shares",
    "pe_basis",
)


def cache_path(session):
    return Path(session.get_bind().url.database).with_suffix(".realtime.json")


@lru_cache(maxsize=4)
def _read(path, modified, size):
    try:
        value = json.loads(Path(path).read_text())
        return value if value.get("version") == 1 else {}
    except (OSError, ValueError, AttributeError):
        return {}


def read_cache(session):
    path = cache_path(session)
    try:
        stat = path.stat()
        return _read(str(path), stat.st_mtime_ns, stat.st_size)
    except OSError:
        return {}


def snapshot_for(session):
    # Pin one immutable generation for all work performed by this HTTP request.
    if "realtime" not in session.info:
        snapshot = read_cache(session)
        published = session.scalar(select(func.max(Publication.trade_date)))
        date = snapshot.get("trade_date")
        now = datetime.now(TZ)
        today = now.strftime("%Y%m%d")
        expected = expected_date(session, now)
        if expected and expected > (snapshot.get("expected_date") or ""):
            snapshot = dict(snapshot, expected_date=expected)
        session.info["realtime"] = (
            snapshot
            if date
            and date <= today
            and (not published or date >= published)
            and snapshot.get("quotes")
            else None
        )
    return session.info["realtime"]


def overlay(item, snapshot):
    if not snapshot:
        return item
    row = snapshot["quotes"].get(item["ts_code"])
    item.update({key: row.get(key) if row else None for key in FIELDS})
    item.update(
        quote_date=row["date"] if row else None,
        quote_time=row["time"] if row else None,
        quote_source=snapshot["source"],
        quote_mode="live",
        status="trading" if row else "unavailable",
        quote_stale=cache_stale(snapshot),
    )
    if row and row.get("name"):
        item["name"] = row["name"]
    return item


def current_bar(result, session, stock):
    snapshot = snapshot_for(session)
    row = snapshot["quotes"].get(stock.ts_code) if snapshot else None
    if not row or any(positive(row.get(k)) is None for k in ("open", "high", "low", "close")):
        return result
    if row["low"] > min(row["open"], row["close"]) or row["high"] < max(row["open"], row["close"]):
        return result
    points = result["points"]
    if points and row["date"] < points[-1]["date"]:
        return result
    if result["adjustment"] == "qfq":
        previous = [p for p in points if p["date"] < row["date"] and p["close"] is not None]
        # Corporate actions can change the prior close. Do not splice incompatible bases.
        if (
            not previous
            or row.get("pre_close") is None
            or abs(previous[-1]["close"] - row["pre_close"]) > 0.011
        ):
            result["message"] = (
                result.get("message") or ""
            ) + "；当日报价已更新，复权基准尚待校验，当日 K 线暂不拼接。"
            return result
    point = dict(
        date=row["date"],
        status="trading",
        **{k: row[k] for k in ("open", "high", "low", "close", "volume")},
    )
    result["points"] = [p for p in points if p["date"] != row["date"]] + [point]
    result["complete"] = False
    result["message"] = "；".join(
        filter(
            None, [result.get("message"), "最新交易日 K 线随免费行情更新，历史日线以盘后同步为准。"]
        )
    )
    return result


def expected_date(session, now):
    return session.scalar(
        select(func.max(Calendar.date)).where(
            Calendar.exchange == "SSE",
            Calendar.is_open.is_(True),
            Calendar.date <= now.strftime("%Y%m%d"),
        )
    )


def cache_stale(snapshot, now=None):
    now = now or datetime.now(TZ)
    if not snapshot:
        return True
    if snapshot.get("error"):
        return True
    if snapshot["trade_date"] < (snapshot.get("expected_date") or snapshot["trade_date"]):
        return True
    # Different symbols update at different times. Delay is acceptable; expose the
    # source timestamp instead of treating an inactive stock as a failed batch.
    return False


def validate_snapshot(rows, stocks, expected, now):
    codes = {s.ts_code for s in stocks}
    candidates = {}
    for row in rows:
        code = row.get("ts_code")
        if code not in codes:
            continue
        if code in candidates:
            raise ProviderError("免费行情存在重复股票代码")
        date = date_text(row.get("date"))
        clock = str(row.get("time") or "")
        try:
            at = datetime.strptime(date + clock, "%Y%m%d%H%M%S").replace(tzinfo=TZ)
        except ValueError:
            continue
        if len(clock) != 6 or at > now + timedelta(minutes=5):
            continue
        if positive(row.get("close")) is None or numeric(row.get("pct_chg")) is None:
            continue
        clean = {k: numeric(row.get(k)) for k in FIELDS if k != "pe_basis"}
        clean.update(date=date, time=clock, name=row.get("name"), pe_basis=row.get("pe_basis"))
        candidates[code] = clean
    date = max((r["date"] for r in candidates.values()), default=None)
    if not date or (expected and date < expected):
        raise ProviderError(f"免费源尚未返回 {expected or '最近交易日'} 的有效行情")
    quotes = {code: row for code, row in candidates.items() if row["date"] == date}
    coverage = {}
    for market in {s.exchange for s in stocks}:
        members = [s.ts_code for s in stocks if s.exchange == market]
        valid = sum(code in quotes for code in members)
        coverage[market] = {"valid": valid, "total": len(members)}
        if valid / len(members) < 0.95:
            raise ProviderError(
                f"{market} 当日行情覆盖不足 95%（{valid}/{len(members)}），保留上次有效行情"
            )
    if not stocks:
        raise ProviderError("股票名单尚未初始化")
    return dict(
        version=1,
        trade_date=date,
        expected_date=max(expected or date, date),
        quotes=quotes,
        coverage=coverage,
        oldest_time=min(r["time"] for r in quotes.values()),
        latest_time=max(r["time"] for r in quotes.values()),
        fetched_at=now.isoformat(),
        error=None,
    )


def write_cache(path, value):
    temporary = path.with_suffix(f".json.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False))
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def refresh(sessions=Session, provider_factory=FreeProvider, now=None):
    fixed_now = now
    now = now or datetime.now(TZ)
    with sessions() as session:
        path = cache_path(session)
        stocks = list(
            session.scalars(
                select(Stock).where(
                    Stock.list_status == "L",
                    Stock.list_date <= now.strftime("%Y%m%d"),
                )
            )
        )
        expected = expected_date(session, now)
        previous_date = read_cache(session).get("trade_date")
        if previous_date and previous_date <= now.strftime("%Y%m%d"):
            expected = max(expected or previous_date, previous_date)
    if not stocks:
        raise ProviderError("股票名单尚未初始化，请先运行 bootstrap")
    # Separate from the daily-sync lock; neither job overwrites the other's data.
    with path.with_suffix(".realtime.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return None
        provider = provider_factory()
        errors = []
        try:
            for source, fetch in (
                (
                    "免费公开行情 · 腾讯",
                    lambda: provider.tencent_snapshot([s.ts_code for s in stocks]),
                ),
                ("免费公开行情 · 东方财富", provider.eastmoney_snapshot),
            ):
                try:
                    value = validate_snapshot(
                        fetch(), stocks, expected, fixed_now or datetime.now(TZ)
                    )
                    value["source"] = source
                    write_cache(path, value)
                    log.info(
                        "免费当日行情 %s：%d 只，%s",
                        value["trade_date"],
                        len(value["quotes"]),
                        source,
                    )
                    return value
                except Exception as exc:
                    errors.append(f"{source}：{exc}")
            with sessions() as session:
                old = dict(read_cache(session))
            old.update(
                version=1,
                error="；".join(errors),
                attempted_at=now.isoformat(),
                expected_date=expected,
            )
            write_cache(path, old)
            raise ProviderError(old["error"])
        finally:
            provider.close()


def start_worker():
    stop = threading.Event()
    if os.getenv("REALTIME_QUOTES", "1") == "0":
        return stop

    def work():
        while not stop.is_set():
            try:
                refresh()
            except Exception:
                log.exception("免费当日行情更新失败")
            now = datetime.now(TZ)
            interval = 120 if "091500" <= now.strftime("%H%M%S") <= "161000" else 900
            stop.wait(interval)

    thread = threading.Thread(target=work, name="free-market-quotes", daemon=True)
    thread.start()
    return stop
