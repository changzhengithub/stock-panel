"""Shared browsing universe, evaluated against current metadata and published ST flags."""

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select

from app.models import Publication, Quote, Stock


def visible_stock():
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
    return and_(
        Stock.list_status == "L",
        or_(Stock.delist_date.is_(None), Stock.delist_date == "", Stock.delist_date > today),
        ~func.upper(Stock.name).contains("ST"),
        ~Stock.name.contains("退"),
        ~flagged_st,
    )
