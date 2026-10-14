import json
from calendar import monthrange
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.orm import aliased

from app.db import Session
from app.jobs.locks import sync_running
from app.jobs.sync import cutoff
from app.models import (
    Calendar,
    Concept,
    ConceptMember,
    Factor,
    HistoryBar,
    HistoryImport,
    Industry,
    IndustryIndexQuote,
    IndustrySnapshot,
    Publication,
    Quote,
    Representative,
    RepresentativeL2,
    Stock,
    SyncRun,
)
from app.providers.free import SOURCE, free_cutoff
from app.realtime import cache_stale, current_bar, overlay, read_cache, snapshot_for
from app.schemas import ConceptInfo, DataStatus, IndustryInfo, PriceSeries, StockInfo, StockList
from app.settings import data_provider
from app.universe import visible_stock

router = APIRouter(prefix="/api")
IndustryL2 = aliased(Industry)


def database():
    with Session() as session:
        yield session


def latest(session):
    return session.scalar(select(func.max(Publication.trade_date)))


def item(row, representative_level=1, fallback_to_l1=False, live=None):
    stock, industry, industry_l2, quote, representative_l1, representative_l2 = row
    representative = representative_l2 if representative_level == 2 else representative_l1
    if fallback_to_l1 and representative is None:
        representative = representative_l1
    actual_level = 2 if representative is representative_l2 and representative is not None else 1
    name_st = "ST" in stock.name.upper()
    result = dict(
        id=stock.id,
        code=stock.symbol,
        ts_code=stock.ts_code,
        name=stock.name,
        industry_id=stock.industry_id,
        industry=industry,
        industry_l2_id=stock.industry_l2_id,
        industry_l2=industry_l2,
        board=stock.board,
        exchange=stock.exchange,
        list_date=stock.list_date,
        fullname=stock.fullname,
        introduction=stock.introduction,
        main_business=stock.main_business,
        updated_at=stock.updated_at,
        close=quote.close if quote else None,
        pct_chg=quote.pct_chg if quote else None,
        amount=quote.amount if quote else None,
        market_cap=quote.market_cap if quote else None,
        float_market_cap=quote.float_market_cap if quote else None,
        turnover_rate=quote.turnover_rate if quote else None,
        pe_ratio=quote.pe_ratio if quote else None,
        pe_basis=quote.pe_basis if quote else None,
        pb_ratio=quote.pb_ratio if quote else None,
        total_shares=quote.total_shares if quote else None,
        float_shares=quote.float_shares if quote else None,
        quote_date=quote.trade_date if quote and quote.status != "unavailable" else None,
        quote_time=None,
        quote_mode="daily",
        quote_source=None,
        quote_stale=False,
        **{
            key: getattr(quote, key, None) if quote else None
            for key in ("open", "high", "low", "volume", "pre_close")
        },
        status=quote.status if quote else "unavailable",
        is_st=quote.is_st if quote and quote.is_st is not None else name_st,
        st_source=quote.st_source if quote and quote.is_st is not None else "current_name",
        representative=None
        if representative is None
        else dict(
            reason=representative.reason,
            reviewed_at=representative.reviewed_at,
            weight_date=representative.weight_date,
            source_url=representative.source_url,
            industry_level=actual_level,
        ),
    )
    return overlay(result, live)


def current_stock_list(
    session, query, live, industry_level, sort, page, page_size, neighbor_of, group_by, filters
):
    """Sort the entire filtered live universe before pagination, never just one page."""
    values = [
        item(r, industry_level, fallback_to_l1=True, live=live)
        for r in session.execute(query).all()
    ]
    if sort.startswith("pct_"):
        values = [v for v in values if v["status"] == "trading" and v["pct_chg"] is not None]
    if sort != "default":
        field, direction = sort.rsplit("_", 1)
        key = {"pct": "pct_chg", "turnover": "turnover_rate"}.get(field, field)
        sign = -1 if direction == "desc" else 1
        values.sort(key=lambda v: (v[key] is None, sign * (v[key] or 0), v["code"], v["exchange"]))
    total = len(values)
    result = dict(
        items=[],
        groups=[],
        total=total,
        matched_stocks=total,
        pagination_unit="stock",
        page=page,
        page_size=page_size,
        trade_date=live["trade_date"],
    )
    if neighbor_of is not None:
        ids = [v["id"] for v in values]
        position = ids.index(neighbor_of) if neighbor_of in ids else -1
        result["navigation"] = dict(
            previous_id=ids[position - 1] if position > 0 else None,
            next_id=ids[position + 1] if 0 <= position < total - 1 else None,
            position=position + 1,
            total=total,
        )
    elif group_by == "industry":
        counts = session.execute(
            select(Industry.id, Industry.name, func.count(Stock.id))
            .join(Stock, Stock.industry_id == Industry.id)
            .where(*filters)
            .group_by(Industry.id)
            .order_by(Industry.id)
        ).all()
        result.update(total=len(counts), pagination_unit="industry")
        result["groups"] = [
            dict(
                id=identity,
                name=name,
                stock_count=count,
                items=[v for v in values if v["industry_id"] == identity],
            )
            for identity, name, count in counts[(page - 1) * page_size : page * page_size]
        ]
    else:
        result["items"] = values[(page - 1) * page_size : page * page_size]
    return result


def base_query(date):
    return (
        select(Stock, Industry.name, IndustryL2.name, Quote, Representative, RepresentativeL2)
        .select_from(Stock)
        .join(Industry, Industry.id == Stock.industry_id)
        .outerjoin(IndustryL2, IndustryL2.id == Stock.industry_l2_id)
        .outerjoin(Quote, (Quote.stock_id == Stock.id) & (Quote.trade_date == date))
        .outerjoin(
            Representative,
            (Representative.stock_id == Stock.id)
            & (Representative.industry_id == Stock.industry_id),
        )
        .outerjoin(
            RepresentativeL2,
            (RepresentativeL2.stock_id == Stock.id)
            & (RepresentativeL2.industry_id == Stock.industry_l2_id),
        )
    )


def market_filters(exchange, board, session=None):
    board_exchange = {
        "沪市主板": "SSE",
        "科创板": "SSE",
        "深市主板": "SZSE",
        "创业板": "SZSE",
        "北交所": "BSE",
    }
    if exchange and board and board_exchange[board] != exchange:
        raise HTTPException(422, "上市板块与交易所市场不匹配")
    filters = [visible_stock(session)]
    if exchange:
        filters.append(Stock.exchange == exchange)
    if board:
        filters.append(Stock.board == board)
    return filters


@router.get("/industries", response_model=list[IndustryInfo])
def industries(
    level: int = Query(1, ge=1, le=2),
    exchange: Literal["SSE", "SZSE", "BSE"] | None = None,
    board: Literal["沪市主板", "深市主板", "创业板", "科创板", "北交所"] | None = None,
    session: DBSession = Depends(database),
):
    stock_filters = market_filters(exchange, board, session)
    if level == 2 and not session.get(IndustrySnapshot, 1):
        return []
    stock_industry = Stock.industry_id if level == 1 else Stock.industry_l2_id
    representative = Representative if level == 1 else RepresentativeL2
    counts = session.execute(
        select(
            Industry.id,
            Industry.name,
            Industry.parent_id,
            func.count(Stock.id),
            func.count(representative.stock_id),
        )
        .select_from(Industry)
        .outerjoin(Stock, and_(stock_industry == Industry.id, *stock_filters))
        .outerjoin(
            representative,
            (representative.stock_id == Stock.id) & (representative.industry_id == Industry.id),
        )
        .where(Industry.level == level)
        .group_by(Industry.id)
        .order_by(Industry.parent_id, Industry.id)
    ).all()
    parents = dict(
        session.execute(select(Industry.id, Industry.name).where(Industry.level == 1)).all()
    )
    result = [
        {
            "id": identity,
            "name": name,
            "level": level,
            "parent_id": parent_id,
            "parent_name": parents.get(parent_id),
            "stock_count": count,
            "representative_count": reps,
        }
        for identity, name, parent_id, count, reps in counts
    ]
    if level == 2:
        missing = session.scalar(
            select(func.count())
            .select_from(Stock)
            .where(*stock_filters, Stock.industry_l2_id.is_(None))
        )
        if missing:
            result.append(
                {
                    "id": "unclassified-l2",
                    "name": "未细分",
                    "level": 2,
                    "parent_id": None,
                    "parent_name": None,
                    "stock_count": missing,
                    "representative_count": 0,
                }
            )
    return result


@router.get("/concepts", response_model=list[ConceptInfo])
def concepts(
    exchange: Literal["SSE", "SZSE", "BSE"] | None = None,
    board: Literal["沪市主板", "深市主板", "创业板", "科创板", "北交所"] | None = None,
    session: DBSession = Depends(database),
):
    filters = market_filters(exchange, board, session)
    rows = session.execute(
        select(Concept, func.count(Stock.id))
        .outerjoin(ConceptMember, ConceptMember.concept_id == Concept.id)
        .outerjoin(Stock, and_(Stock.id == ConceptMember.stock_id, *filters))
        .group_by(Concept.id)
        .order_by(Concept.name)
    ).all()
    available = {}
    for concept, count in rows:
        previous = available.get(concept.name)
        if previous is None or (bool(concept.fetched_at), concept.id.startswith("TDX:")) > (
            bool(previous[0].fetched_at),
            previous[0].id.startswith("TDX:"),
        ):
            available[concept.name] = (concept, count)
    ordered = sorted(available.values(), key=lambda row: (not bool(row[0].fetched_at), row[0].name))
    return [
        dict(
            id=concept.id,
            name=concept.name,
            stock_count=count,
            source=concept.source,
            fetched_at=concept.fetched_at,
            error=concept.error,
        )
        for concept, count in ordered
    ]


@router.get("/stocks", response_model=StockList)
def stocks(
    keyword: str = Query("", max_length=80),
    industry_id: str | None = None,
    industry_level: int = Query(1, ge=1, le=2),
    concept_id: str | None = None,
    exchange: Literal["SSE", "SZSE", "BSE"] | None = None,
    board: Literal["沪市主板", "深市主板", "创业板", "科创板", "北交所"] | None = None,
    scope: Literal["all", "representatives"] = "all",
    sort: Literal[
        "default",
        "pct_desc",
        "pct_asc",
        "market_cap_desc",
        "market_cap_asc",
        "close_desc",
        "close_asc",
        "amount_desc",
        "amount_asc",
        "turnover_desc",
        "turnover_asc",
    ] = "default",
    codes: str | None = Query(None, max_length=10000),
    neighbor_of: int | None = None,
    group_by: Literal["none", "industry"] = "none",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    session: DBSession = Depends(database),
):
    if industry_level == 2 and not session.get(IndustrySnapshot, 1):
        raise HTTPException(503, "二级行业尚未同步，请稍后重试")
    if group_by == "industry" and (
        industry_level != 1 or scope != "representatives" or sort != "default"
    ):
        raise HTTPException(422, "行业分组仅支持一级代表股默认排序")
    date = latest(session)
    live = snapshot_for(session)
    filters = market_filters(exchange, board, session)
    if industry_id:
        if industry_level == 2 and industry_id == "unclassified-l2":
            filters.append(Stock.industry_l2_id.is_(None))
        else:
            industry = session.get(Industry, industry_id)
            if not industry or industry.level != industry_level:
                raise HTTPException(422, "行业代码与所选层级不匹配")
            filters.append(
                (Stock.industry_id if industry_level == 1 else Stock.industry_l2_id) == industry_id
            )
    if concept_id:
        concept = session.get(Concept, concept_id)
        if not concept:
            raise HTTPException(422, "概念板块不存在")
        if not concept.fetched_at:
            detail = (
                f"{concept.name}成分同步失败，当前数据源暂不可用"
                if concept.error
                else f"{concept.name}成分尚未同步"
            )
            raise HTTPException(503, detail)
        filters.append(
            Stock.id.in_(
                select(ConceptMember.stock_id).where(ConceptMember.concept_id == concept_id)
            )
        )
        if scope == "representatives":
            raise HTTPException(422, "概念板块不支持龙头股筛选")
    if keyword.strip():
        filters.append(
            or_(
                Stock.name.contains(keyword.strip(), autoescape=True),
                Stock.symbol.contains(keyword.strip(), autoescape=True),
            )
        )
    if codes is not None:
        filters.append(Stock.ts_code.in_(codes.split(",") if codes else []))
    query = base_query(date).where(*filters)
    if scope == "representatives":
        representative = Representative if industry_level == 1 else RepresentativeL2
        query = query.where(representative.stock_id.is_not(None))
    if sort.startswith("pct_") and not live:
        query = query.where(Quote.status == "trading", Quote.pct_chg.is_not(None))
    ordering = [Stock.symbol, Stock.exchange]
    if sort == "pct_desc":
        ordering.insert(0, Quote.pct_chg.desc())
    elif sort == "pct_asc":
        ordering.insert(0, Quote.pct_chg.asc())
    elif sort != "default":
        field, direction = sort.rsplit("_", 1)
        column = {
            "market_cap": Quote.market_cap,
            "close": Quote.close,
            "amount": Quote.amount,
            "turnover": Quote.turnover_rate,
        }[field]
        ordering = [
            column.is_(None),
            column.desc() if direction == "desc" else column.asc(),
        ] + ordering
    elif scope == "representatives":
        ordering = (
            [Industry.id, Representative.position]
            if industry_level == 1
            else [RepresentativeL2.industry_id, RepresentativeL2.position]
        ) + ordering
    if sort == "default" and codes:
        ordering = [
            case({code: i for i, code in enumerate(codes.split(","))}, value=Stock.ts_code)
        ] + ordering
    if live:
        return current_stock_list(
            session,
            query.order_by(*ordering),
            live,
            industry_level,
            sort,
            page,
            page_size,
            neighbor_of,
            group_by,
            filters,
        )
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    if neighbor_of is not None:
        ordered_ids = list(session.scalars(query.with_only_columns(Stock.id).order_by(*ordering)))
        position = ordered_ids.index(neighbor_of) if neighbor_of in ordered_ids else -1
        return dict(
            items=[],
            groups=[],
            total=total,
            matched_stocks=total,
            pagination_unit="stock",
            page=page,
            page_size=page_size,
            trade_date=date,
            navigation=dict(
                previous_id=ordered_ids[position - 1] if position > 0 else None,
                next_id=ordered_ids[position + 1] if 0 <= position < len(ordered_ids) - 1 else None,
                position=position + 1,
                total=total,
            ),
        )
    if group_by == "industry":
        group_query = (
            select(Industry.id, Industry.name, func.count(Stock.id))
            .select_from(Industry)
            .join(Stock, Stock.industry_id == Industry.id)
            .where(*filters)
            .group_by(Industry.id)
            .order_by(Industry.id)
        )
        group_total = session.scalar(select(func.count()).select_from(group_query.subquery()))
        group_rows = session.execute(
            group_query.offset((page - 1) * page_size).limit(page_size)
        ).all()
        groups = []
        for identity, name, count in group_rows:
            rows = session.execute(
                query.where(Stock.industry_id == identity).order_by(*ordering)
            ).all()
            groups.append(
                {
                    "id": identity,
                    "name": name,
                    "stock_count": count,
                    "items": [item(r) for r in rows],
                }
            )
        return {
            "items": [],
            "groups": groups,
            "total": group_total,
            "matched_stocks": total,
            "pagination_unit": "industry",
            "page": page,
            "page_size": page_size,
            "trade_date": date,
        }
    rows = session.execute(
        query.order_by(*ordering).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [item(r, industry_level, fallback_to_l1=True) for r in rows],
        "groups": [],
        "total": total,
        "matched_stocks": total,
        "pagination_unit": "stock",
        "page": page,
        "page_size": page_size,
        "trade_date": date,
    }


@router.get("/search")
def search(keyword: str = Query("", max_length=80), session: DBSession = Depends(database)):
    from app.search import search_stocks

    return search_stocks(session, keyword)


@router.get("/industry-summary")
def industry_summary(
    background_tasks: BackgroundTasks,
    industry_id: str | None = None,
    industry_level: int = Query(1, ge=1, le=2),
    concept_id: str | None = None,
    exchange: Literal["SSE", "SZSE", "BSE"] | None = None,
    board: Literal["沪市主板", "深市主板", "创业板", "科创板", "北交所"] | None = None,
    session: DBSession = Depends(database),
):
    date = latest(session)
    live = snapshot_for(session)
    filters = market_filters(exchange, board, session)
    industry = session.get(Industry, industry_id) if industry_id else None
    if industry_id:
        if industry_id == "unclassified-l2" and industry_level == 2:
            filters.append(Stock.industry_l2_id.is_(None))
        elif not industry or industry.level != industry_level:
            raise HTTPException(422, "行业与层级不匹配")
        else:
            filters.append(
                (Stock.industry_id if industry_level == 1 else Stock.industry_l2_id) == industry_id
            )
    if concept_id:
        concept = session.get(Concept, concept_id)
        if not concept or not concept.fetched_at:
            raise HTTPException(503, "概念成分尚未同步")
        filters.append(
            Stock.id.in_(
                select(ConceptMember.stock_id).where(ConceptMember.concept_id == concept_id)
            )
        )
    rows = session.execute(
        select(Quote.status, Quote.pct_chg)
        .select_from(Stock)
        .outerjoin(Quote, (Stock.id == Quote.stock_id) & (Quote.trade_date == date))
        .where(*filters)
    ).all()
    if live:
        codes = session.scalars(select(Stock.ts_code).where(*filters)).all()
        rows = [
            ("trading", live["quotes"][code]["pct_chg"])
            if code in live["quotes"]
            else ("unavailable", None)
            for code in codes
        ]
        date = live["trade_date"]
    valid = [pct for state, pct in rows if state == "trading" and pct is not None]
    index = (
        session.get(IndustryIndexQuote, (industry_id, date))
        if industry and date and not concept_id
        else None
    )
    pending = False
    if industry and date and not concept_id and industry_id[:6].isdigit():
        recent = (
            index
            and (
                datetime.now().astimezone() - datetime.fromisoformat(index.fetched_at)
            ).total_seconds()
            < 300
        )
        if not index or (index.error and not recent):
            from app.jobs.index_quotes import warm_index

            background_tasks.add_task(warm_index, industry_id, date)
            pending = True
    return dict(
        trade_date=date,
        total=len(rows),
        valid=len(valid),
        missing=len(rows) - len(valid),
        up=sum(p > 0 for p in valid),
        down=sum(p < 0 for p in valid),
        flat=sum(p == 0 for p in valid),
        index=None
        if not index or index.close is None
        else dict(close=index.close, pct_chg=index.pct_chg, trade_date=index.trade_date),
        index_pending=pending,
        index_message=index.error if index and index.error else None,
    )


@router.get("/stocks/{stock_id}", response_model=StockInfo)
def stock_detail(
    stock_id: int,
    background_tasks: BackgroundTasks,
    industry_level: int = Query(1, ge=1, le=2),
    session: DBSession = Depends(database),
):
    row = session.execute(
        base_query(latest(session)).where(Stock.id == stock_id, visible_stock(session))
    ).first()
    if not row:
        raise HTTPException(404, "股票不存在")
    result = item(row, industry_level, fallback_to_l1=True, live=snapshot_for(session))
    publication = session.get(Publication, latest(session)) if latest(session) else None
    if (
        publication
        and publication.source.startswith("免费公开数据")
        and not result["main_business"]
    ):
        from app.jobs.free_sync import warm_profile

        background_tasks.add_task(warm_profile, stock_id)
        result["profile_pending"] = True
    return result


@router.get("/stocks/{stock_id}/prices", response_model=PriceSeries)
def prices(
    stock_id: int,
    background_tasks: BackgroundTasks,
    range: Literal["1m", "3m", "1y", "3y", "5y", "10y"] = "3m",
    adjustment: Literal["qfq", "none"] = "qfq",
    session: DBSession = Depends(database),
):
    stock = session.scalar(select(Stock).where(Stock.id == stock_id, visible_stock(session)))
    if not stock:
        raise HTTPException(404, "股票不存在")
    end = latest(session)
    if not end:
        return {
            "points": [],
            "basis_date": None,
            "adjustment": adjustment,
            "complete": False,
            "missing_days": [],
            "message": "尚无已发布行情",
        }
    end_dt = datetime.strptime(end, "%Y%m%d")
    months = {"1m": 1, "3m": 3, "1y": 12, "3y": 36, "5y": 60, "10y": 120}[range]
    serial = end_dt.year * 12 + end_dt.month - 1 - months
    year, month = serial // 12, serial % 12 + 1
    start = end_dt.replace(
        year=year, month=month, day=min(end_dt.day, monthrange(year, month)[1])
    ).strftime("%Y%m%d")
    start = max(start, stock.list_date)
    publication = session.get(Publication, end)
    if publication.source.startswith("免费公开数据"):
        return current_bar(
            free_prices(session, stock, start, end, background_tasks, adjustment), session, stock
        )
    anchor = session.get(Factor, (stock_id, end))
    if adjustment == "qfq" and (not anchor or anchor.value <= 0):
        return {
            "points": [],
            "basis_date": end,
            "adjustment": adjustment,
            "complete": False,
            "missing_days": [end],
            "message": "基准日复权因子缺失，暂不展示复权走势",
        }
    rows = session.execute(
        select(Quote, Factor)
        .join(Publication, Publication.trade_date == Quote.trade_date)
        .outerjoin(
            Factor,
            (Factor.stock_id == Quote.stock_id) & (Factor.trade_date == Quote.trade_date),
        )
        .where(
            Quote.stock_id == stock_id,
            Quote.trade_date >= start,
            Quote.trade_date <= end,
        )
    ).all()
    by_date = {q.trade_date: (q, f) for q, f in rows}
    dates = list(
        session.scalars(
            select(Calendar.date)
            .where(
                Calendar.exchange == stock.exchange,
                Calendar.is_open.is_(True),
                Calendar.date >= start,
                Calendar.date <= end,
            )
            .order_by(Calendar.date)
        )
    )
    missing, points = [], []
    for date in dates:
        q, f = by_date.get(date, (None, None))
        candle = None
        if q and q.status == "suspended":
            pass
        elif (
            q
            and (adjustment == "none" or (f and f.value > 0))
            and all(value is not None for value in (q.open, q.high, q.low, q.close))
        ):
            scale = f.value / anchor.value if adjustment == "qfq" else 1
            candle = {
                "open": round(q.open * scale, 4),
                "high": round(q.high * scale, 4),
                "low": round(q.low * scale, 4),
                "close": round(q.close * scale, 4),
                "volume": q.volume,
            }
        else:
            missing.append(date)
        points.append(
            {
                "date": date,
                "status": "suspended"
                if q and q.status == "suspended"
                else "trading"
                if candle
                else "missing",
                **(candle or dict.fromkeys(("open", "high", "low", "close", "volume"))),
            }
        )
    volume_missing = [
        point["date"] for point in points if point["close"] is not None and point["volume"] is None
    ]
    messages = []
    if not dates or missing:
        messages.append("历史 K 线数据尚有缺口，断点处不补造价格")
    if volume_missing:
        messages.append("部分交易日成交量尚未同步，缺失量不补造")
    return current_bar(
        {
            "points": points,
            "basis_date": end,
            "adjustment": adjustment,
            "start_date": start,
            "complete": bool(dates) and not missing,
            "missing_days": missing,
            "message": "；".join(messages) if messages else None,
        },
        session,
        stock,
    )


def free_prices(session, stock, start, end, background_tasks, adjustment="qfq"):
    from app.jobs.free_sync import warm_history

    history = session.get(HistoryImport, stock.id)
    rows = list(
        session.scalars(
            select(HistoryBar)
            .where(
                HistoryBar.stock_id == stock.id,
                HistoryBar.trade_date >= start,
                HistoryBar.trade_date <= end,
            )
            .order_by(HistoryBar.trade_date)
        )
    )
    columns = (
        ("adjusted_open", "adjusted_high", "adjusted_low", "adjusted_close")
        if adjustment == "qfq"
        else ("raw_open", "raw_high", "raw_low", "raw_close")
    )
    usable = [r for r in rows if all(getattr(r, c) is not None for c in columns)]
    refresh = (
        not history
        or history.basis_date != end
        or history.start_date > start
        or history.state == "failed"
        or not rows
        or len(usable) != len(rows)
        or any(r.volume is None for r in rows)
    )
    recent_error = bool(
        history
        and history.error
        and (
            datetime.now().astimezone() - datetime.fromisoformat(history.updated_at)
        ).total_seconds()
        < 300
    )
    pending = refresh and not recent_error
    if pending:
        background_tasks.add_task(warm_history, stock.id, start)
    basis = history.basis_date if history and usable else end
    available_start = max(start, history.start_date) if history and usable else start
    values = {
        r.trade_date: dict(
            zip(("open", "high", "low", "close"), (getattr(r, c) for c in columns)),
            volume=r.volume,
            status="trading",
        )
        for r in usable
    }
    dates = (
        list(
            session.scalars(
                select(Calendar.date)
                .where(
                    Calendar.exchange == stock.exchange,
                    Calendar.is_open.is_(True),
                    Calendar.date >= available_start,
                    Calendar.date <= basis,
                )
                .order_by(Calendar.date)
            )
        )
        if usable
        else []
    )
    missing = [d for d in dates if d not in values]
    messages = []
    if refresh:
        messages.append(
            "正在补充所需历史，完成后自动更新。"
            if pending
            else f"历史更新失败：{history.error if history else '暂无数据'}"
        )
        if usable:
            messages.append(f"保留已缓存历史，截至 {basis}，复权基准保持不变。")
    if missing:
        messages.append("部分交易日数据缺失，免费源无法确认是否停牌；缺失价格不补造。")
    if any(r.volume is None for r in usable):
        messages.append("部分成交量缺失。")
    return dict(
        points=[
            {
                "date": d,
                **values.get(
                    d,
                    dict.fromkeys(("open", "high", "low", "close", "volume"))
                    | {"status": "missing"},
                ),
            }
            for d in dates
        ],
        basis_date=basis,
        start_date=available_start,
        adjustment=adjustment,
        stale=bool(usable and refresh),
        complete=bool(dates) and not missing and not refresh,
        missing_days=missing,
        pending=pending,
        message="；".join(messages) or None,
    )


@router.get("/data-status", response_model=DataStatus)
def data_status(session: DBSession = Depends(database)):
    date = latest(session)
    publication = session.get(Publication, date) if date else None
    free = (
        publication.source.startswith("免费公开数据") if publication else data_provider() == "free"
    )
    run = session.scalar(select(SyncRun).order_by(SyncRun.id.desc()).limit(1))
    end = free_cutoff() if free else cutoff()
    start = (datetime.strptime(end, "%Y%m%d") - timedelta(days=366)).strftime("%Y%m%d")
    calendar_until = session.scalar(
        select(func.max(Calendar.date)).where(Calendar.exchange == "SSE")
    )
    expected = list(
        session.scalars(
            select(Calendar.date).where(
                Calendar.exchange == "SSE",
                Calendar.is_open.is_(True),
                Calendar.date >= start,
                Calendar.date <= end,
            )
        )
    )
    published = set(session.scalars(select(Publication.trade_date)))
    missing = [d for d in expected if d not in published]
    count = session.scalar(select(func.count()).select_from(Stock).where(visible_stock(session)))
    unclassified = session.scalar(
        select(func.count())
        .select_from(Stock)
        .where(visible_stock(session), Stock.industry_id == "unclassified")
    )
    industry_snapshot = session.get(IndustrySnapshot, 1)
    level2_count = session.scalar(
        select(func.count()).select_from(Industry).where(Industry.level == 2)
    )
    level2_unclassified = session.scalar(
        select(func.count())
        .select_from(Stock)
        .where(visible_stock(session), Stock.industry_l2_id.is_(None))
    )
    industry_synced_date = (
        datetime.fromisoformat(industry_snapshot.fetched_at)
        .astimezone(ZoneInfo("Asia/Shanghai"))
        .strftime("%Y%m%d")
        if industry_snapshot
        else None
    )
    run_data = (
        None
        if not run
        else {
            "state": run.state,
            "started_at": run.started_at,
            "ended_at": run.ended_at,
            "progress": run.progress,
            "error": run.error,
            "warnings": json.loads(run.warnings),
        }
    )
    if run_data and run_data["state"] == "running" and sync_running() is False:
        run_data["state"] = "interrupted"
        run_data["error"] = "同步进程已结束但未完成，可运行 sync 继续补齐。"
    history_info = {
        "complete": bool(expected) and not missing,
        "expected_days": len(expected),
        "published_days": len(set(expected) & published),
        "missing_days": missing,
        "start_date": min(expected) if expected else None,
        "unit": "trading_day",
    }
    if free:
        eligible = list(
            session.scalars(
                select(Stock).where(visible_stock(session), Stock.list_date <= (date or end))
            )
        )
        imports = {r.stock_id: r for r in session.scalars(select(HistoryImport))}
        completed = sum(
            1
            for stock in eligible
            if (h := imports.get(stock.id))
            and h.state == "complete"
            and h.basis_date == date
            and h.start_date <= max(start, stock.list_date)
        )
        history_info = {
            "complete": bool(eligible) and completed == len(eligible),
            "expected_days": len(eligible),
            "published_days": completed,
            "missing_days": [],
            "start_date": start,
            "unit": "stock",
        }
    result = {
        "daily_trade_date": date,
        "available": bool(date),
        "trade_date": date,
        "expected_date": max(expected) if expected else None,
        "stale": bool(
            date
            and (not calendar_until or calendar_until < end or (expected and date != max(expected)))
        ),
        "stock_count": count,
        "unclassified_count": unclassified,
        "source": publication.source if publication else SOURCE if free else "Tushare Pro",
        "missing_quote_count": publication.missing_count if publication else 0,
        "missing_cap_count": publication.missing_cap_count if publication else 0,
        "industry_source": (industry_snapshot.source if industry_snapshot else "SW2021 一级行业"),
        "industry_synced_at": industry_snapshot.fetched_at if industry_snapshot else None,
        "industry_source_updated_at": (
            industry_snapshot.source_updated_at if industry_snapshot else None
        ),
        "industry_l2_available": bool(industry_snapshot and level2_count == 134),
        "industry_l2_count": level2_count,
        "industry_l2_unclassified_count": level2_unclassified,
        "industry_stale": bool(
            not industry_synced_date or (expected and industry_synced_date < max(expected))
        ),
        "history": history_info,
        "last_run": run_data,
    }

    live = snapshot_for(session)
    state = read_cache(session)
    result["quote_error"] = state.get("error")
    if live:
        eligible_codes = session.scalars(select(Stock.ts_code).where(visible_stock(session))).all()
        valid = [live["quotes"][code] for code in eligible_codes if code in live["quotes"]]
        result.update(
            available=True,
            trade_date=live["trade_date"],
            expected_date=live.get("expected_date"),
            stale=cache_stale(live),
            source=live["source"],
            quote_mode="live",
            quote_time=live["latest_time"],
            quote_oldest_time=live["oldest_time"],
            quote_fetched_at=live["fetched_at"],
            quote_coverage=live["coverage"],
            missing_quote_count=len(eligible_codes) - len(valid),
            missing_cap_count=sum(row.get("market_cap") is None for row in valid),
        )
    elif state.get("error"):
        result["stale"] = True
    return result
