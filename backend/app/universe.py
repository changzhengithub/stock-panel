"""Shared browsing universe, evaluated against current metadata and published ST flags."""

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select

from app.models import Publication, Quote, Stock
from app.realtime import snapshot_for


def visible_stock(session=None):
    today = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d")
    published_date = select(func.max(Publication.trade_date)).scalar_subquery()
    flagged_st = (
        select(Quote.stock_id)
        .where(
            Quote.stock_id == Stock.id,
            Quote.trade_date == published_date,
            Quote.is_st.is_(True),
        )
        .correlate(Stock)
        .exists()
    )
    live_flags = []
    if session is not None:
        snapshot = snapshot_for(session) or {}
        live_flags = [
            code
            for code, row in snapshot.get("quotes", {}).items()
            if "ST" in (row.get("name") or "").upper() or "退" in (row.get("name") or "")
        ]
    return and_(
        Stock.list_status == "L",
        or_(Stock.delist_date.is_(None), Stock.delist_date == "", Stock.delist_date > today),
        ~func.upper(Stock.name).contains("ST"),
        ~Stock.name.contains("退"),
        ~flagged_st,
        Stock.ts_code.not_in(live_flags),
    )
