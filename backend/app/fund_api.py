"""Cached fund rankings and same-source board details."""

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.api import database
from app.fund_flow import board_id, enabled, read, refresh_pending, request_refresh, scope
from app.models import CodeAlias, FundBoard, FundRun, Stock
from app.providers.fund_flow import SOURCE, TZ
from app.realtime import expected_date
from app.universe import visible_stock

router = APIRouter(prefix="/api/hot-sectors", tags=["热门板块"])
Kind = Literal["concept", "industry"]
Period = Literal["today", "5d", "10d"]
Sort = Literal["net_desc", "net_asc", "rate_desc", "rate_asc", "pct_desc", "pct_asc"]


def metadata(session, key, data, period):
    run = session.get(FundRun, key)
    now = datetime.now(timezone.utc)
    pending = bool(
        run
        and not run.finished_at
        and (now - datetime.fromisoformat(run.started_at)).total_seconds() < 150
    )
    pending = pending or refresh_pending(session, key)
    expected = expected_date(session, datetime.now(TZ))
    error = run.error if run else None
    date = data.get("trade_date") if data else None
    stale = bool(error or data and expected and date and date < expected)
    missing = sum(row.get("net_amount") is None for row in data["rows"]) if data else 0
    return dict(
        source=SOURCE,
        classification_source="东方财富板块分类",
        period=period,
        trade_date=date,
        source_as_of=data.get("source_as_of") if data else None,
        window_start=None,
        window_end=date,
        window_note="来源未提供区间起点" if period != "today" and period != "daily" else None,
        fetched_at=data.get("fetched_at") if data else None,
        batch_id=data.get("batch_id") if data else None,
        pending=pending,
        stale=stale,
        error=error,
        retry_at=run.retry_at if run else None,
        quality_status="partial" if missing else "available" if data else "unavailable",
        missing_count=missing,
        valid_count=len(data["rows"]) - missing if data else 0,
        auto_update=enabled(),
    )


def sorted_rows(rows, sort):
    field, direction = sort.split("_")
    key = {"net": "net_amount", "rate": "net_rate", "pct": "pct_change"}[field]
    sign = -1 if direction == "desc" else 1
    return sorted(rows, key=lambda r: (r.get(key) is None, sign * (r.get(key) or 0), r["code"]))


def board_or_404(session, identity):
    board = session.get(FundBoard, identity)
    if not board:
        raise HTTPException(404, "板块不存在或尚未同步")
    return board


def stock_links(session, rows):
    """Map only verified codes; filtering is shared with every market entry point."""
    all_stocks = list(session.scalars(select(Stock)))
    aliases = dict(session.execute(select(CodeAlias.code, CodeAlias.stock_id)).all())
    by_code = {s.ts_code: s.id for s in all_stocks}
    by_code.update(aliases)
    by_symbol = {}
    for stock in all_stocks:
        by_symbol.setdefault(stock.symbol, []).append(stock.id)
    visible = set(session.scalars(select(Stock.id).where(visible_stock(session))))
    result, filtered, unmatched = [], 0, 0
    for row in rows:
        identity = by_code.get(row.get("ts_code"))
        if identity is None:
            unmatched += 1
            continue
        if identity not in visible:
            filtered += 1
            continue
        result.append({**row, "stock_id": identity})
    return result, filtered, unmatched, by_symbol, visible


@router.get("")
def ranking(
    kind: Kind = "concept",
    period: Period = "today",
    keyword: str = Query("", max_length=80),
    direction: Literal["all", "in", "out"] = "all",
    sort: Sort = "net_desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: DBSession = Depends(database),
):
    if page_size not in (20, 50, 100):
        raise HTTPException(422, "每页条数仅支持 20、50、100")
    key = scope(kind, period)
    data = read(session, key)
    request_refresh(session, kind, period)
    full = data["rows"] if data else []
    positive = [r for r in full if r["net_amount"] is not None and r["net_amount"] > 0]
    negative = [r for r in full if r["net_amount"] is not None and r["net_amount"] < 0]

    def annotate(r):
        return {**r, "id": board_id(kind, r["code"]), "kind": kind}

    overview = dict(
        valid_count=sum(r["net_amount"] is not None for r in full),
        total_count=len(full),
        top_in=annotate(max(positive, key=lambda r: r["net_amount"])) if positive else None,
        top_out=annotate(min(negative, key=lambda r: r["net_amount"])) if negative else None,
    )
    rows = [r for r in full if keyword.strip().lower() in (r["name"] + r["code"]).lower()]
    if direction != "all":
        rows = [
            r
            for r in rows
            if r["net_amount"] is not None
            and (r["net_amount"] > 0 if direction == "in" else r["net_amount"] < 0)
        ]
    rows = sorted_rows(rows, sort)
    offset = (page - 1) * page_size
    return dict(
        items=[
            {**annotate(r), "rank": offset + i + 1}
            for i, r in enumerate(rows[offset : offset + page_size])
        ],
        total=len(rows),
        page=page,
        page_size=page_size,
        overview=overview,
        chart={
            "inflows": [annotate(r) for r in sorted_rows(positive, "net_desc")[:10]],
            "outflows": [annotate(r) for r in sorted_rows(negative, "net_asc")[:10]],
        },
        meta=metadata(session, key, data, period),
    )


@router.get("/{identity}")
def detail(identity: str, period: Period = "today", session: DBSession = Depends(database)):
    board = board_or_404(session, identity)
    key = scope(board.kind, period)
    data = read(session, key)
    request_refresh(session, board.kind, period)
    today = read(session, scope(board.kind, "today"))
    request_refresh(session, board.kind, "today")

    def find(batch):
        return next((r for r in batch["rows"] if r["code"] == board.code), None) if batch else None

    row, daily = find(data), find(today)
    lead_id, lead_reason = None, None
    if row and row.get("lead_code"):
        candidates = list(
            session.scalars(
                select(Stock).where(Stock.symbol == str(row["lead_code"]), visible_stock(session))
            )
        )
        if len(candidates) == 1:
            lead_id = candidates[0].id
        else:
            lead_reason = "最大资金股被本站过滤或代码无法唯一匹配"
    return dict(
        board=dict(
            id=board.id, kind=board.kind, code=board.code, name=board.name, source=board.source
        ),
        summary=row,
        breakdown=daily,
        lead_stock_id=lead_id,
        lead_unavailable_reason=lead_reason,
        meta=metadata(session, key, data, period),
        breakdown_meta=metadata(session, scope(board.kind, "today"), today, "today"),
    )


@router.get("/{identity}/history")
def history(
    identity: str, days: int = Query(20, ge=1, le=60), session: DBSession = Depends(database)
):
    if days not in (20, 60):
        raise HTTPException(422, "趋势区间仅支持 20、60 交易日")
    board = board_or_404(session, identity)
    key = scope(board.kind, "daily", board.code, "history")
    data = read(session, key)
    request_refresh(session, board.kind, "daily", board.code, "history")
    rows = data["rows"][-days:] if data else []
    # Materialize known trading-day gaps as nulls; never fabricate missing funds as zero.
    if rows:
        from app.models import Calendar

        dates = list(
            session.scalars(
                select(Calendar.date)
                .where(
                    Calendar.exchange == "SSE",
                    Calendar.is_open.is_(True),
                    Calendar.date >= rows[0]["trade_date"],
                    Calendar.date <= rows[-1]["trade_date"],
                )
                .order_by(Calendar.date)
            )
        )
        indexed = {r["trade_date"]: r for r in rows}
        rows = [
            indexed.get(
                day,
                {
                    "trade_date": day,
                    "net_amount": None,
                    "net_rate": None,
                    "provisional": False,
                    "gap": True,
                },
            )
            for day in sorted(set(dates) | set(indexed))
        ][-days:]
    return dict(
        items=rows,
        available_days=len(data["rows"]) if data else 0,
        available_start=data["rows"][0]["trade_date"] if data else None,
        available_end=data["rows"][-1]["trade_date"] if data else None,
        meta=metadata(session, key, data, "daily"),
    )


@router.get("/{identity}/stocks")
def stocks(
    identity: str,
    period: Period = "today",
    sort: Sort = "net_desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: DBSession = Depends(database),
):
    if page_size not in (20, 50, 100):
        raise HTTPException(422, "每页条数仅支持 20、50、100")
    board = board_or_404(session, identity)
    key = scope(board.kind, period, board.code, "stocks")
    data = read(session, key)
    request_refresh(session, board.kind, period, board.code, "stocks")
    full = data["rows"] if data else []
    rows, filtered, unmatched, _, _ = stock_links(session, full)
    rows = sorted_rows(rows, sort)
    offset = (page - 1) * page_size
    return dict(
        items=rows[offset : offset + page_size],
        total=len(rows),
        page=page,
        source_count=len(full),
        filtered_count=filtered,
        unmatched_count=unmatched,
        missing_count=sum(r["net_amount"] is None for r in rows),
        meta=metadata(session, key, data, period),
    )
