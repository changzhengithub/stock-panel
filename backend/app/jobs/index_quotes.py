"""Fetch a selected official index; never substitute constituent averages."""

import threading

from sqlalchemy import select

from app.db import Session
from app.models import Calendar, IndustryIndexQuote, utcnow
from app.providers.free import FreeProvider, date_text, positive

_active = set()
_lock = threading.Lock()


def warm_index(industry_id, date):
    key = (industry_id, date)
    with _lock:
        if key in _active:
            return
        _active.add(key)
    provider = FreeProvider()
    try:
        rows = provider.ak("index_hist_sw", symbol=industry_id[:6], period="day")
        values = {}
        for row in rows:
            day = date_text(row["日期"])
            if str(row["代码"]) != industry_id[:6] or day in values:
                raise ValueError("指数代码或日期校验失败")
            value = positive(row["收盘"])
            if value is None:
                raise ValueError("指数收盘价无效")
            values[day] = value
        with Session() as s:
            previous = s.scalar(
                select(Calendar.date)
                .where(Calendar.exchange == "SSE", Calendar.is_open.is_(True), Calendar.date < date)
                .order_by(Calendar.date.desc())
                .limit(1)
            )
        if date not in values or previous not in values:
            raise ValueError("暂无与行情同日及前一交易日的官方指数数据")
        with Session.begin() as s:
            s.merge(
                IndustryIndexQuote(
                    industry_id=industry_id,
                    trade_date=date,
                    close=values[date],
                    pct_chg=(values[date] / values[previous] - 1) * 100,
                    error=None,
                    fetched_at=utcnow(),
                )
            )
    except Exception as exc:
        with Session.begin() as s:
            old = s.get(IndustryIndexQuote, key)
            if not old or old.close is None:
                s.merge(
                    IndustryIndexQuote(
                        industry_id=industry_id,
                        trade_date=date,
                        error=str(exc),
                        fetched_at=utcnow(),
                    )
                )
    finally:
        provider.close()
        with _lock:
            _active.discard(key)
