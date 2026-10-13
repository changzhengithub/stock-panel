"""Publish the highest-weight constituents of Shenwan industry indices."""

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.db import Session
from app.models import Industry, Representative, RepresentativeL2, Stock
from app.providers.free import stock_code
from app.providers.tushare import ProviderError

SOURCE_URL = "https://www.swsresearch.com/institute_sw/allIndex/releasedIndex/releasedetail?code="
TOP_COUNT = 3


def ranked_components(rows):
    """Reject truncated or malformed source data before changing a published list."""
    if not rows or len(rows) >= 10000:
        raise ProviderError("SW2021 行业指数成分为空或可能被截断")
    weights = {}
    for row in rows:
        code = stock_code(row["证券代码"])
        try:
            weight = float(row["最新权重"])
        except (TypeError, ValueError):
            raise ProviderError(f"SW2021 行业指数成分权重无效：{code}") from None
        if not 0 < weight <= 100 or code in weights:
            raise ProviderError(f"SW2021 行业指数成分权重异常或重复：{code}")
        weights[code] = weight
    if not 97 <= sum(weights.values()) <= 103:
        raise ProviderError("SW2021 行业指数成分权重合计不在 100% 附近")
    return sorted(weights.items(), key=lambda item: (-item[1], item[0]))


def refresh_index_leaders(provider, sessions=Session, progress=None):
    """Replace manual candidates with source-ranked constituents, one industry at a time.

    A failed request keeps an earlier *official* result for that industry, but never
    keeps a former hand-picked list. Categories without a published index stay empty.
    """
    progress = progress or (lambda _: None)
    with sessions() as session:
        industries = list(session.scalars(select(Industry).where(Industry.level.in_((1, 2)))))
        stocks = {
            stock.ts_code: stock
            for stock in session.scalars(select(Stock).where(Stock.list_status == "L"))
        }

    try:
        live_l2 = {
            str(row["指数代码"]) + ".SI"
            for row in provider.ak("index_realtime_sw", symbol="二级行业")
        }
    except (ProviderError, KeyError, ValueError) as exc:
        live_l2 = None
        warnings = [f"SW2021 二级指数列表不可用，保留已获取的官方权重：{exc}"]
    else:
        warnings = []

    candidates = [
        industry
        for industry in industries
        if industry.id != "unclassified"
        and (industry.level == 1 or (live_l2 is not None and industry.id in live_l2))
    ]
    fetched = {}
    failures = 0
    for index, industry in enumerate(candidates, 1):
        progress(f"SW2021 行业指数权重 {index}/{len(candidates)}：{industry.name}")
        try:
            ranked = ranked_components(provider.ak("index_component_sw", symbol=industry.id[:6]))
        except (ProviderError, KeyError, ValueError) as exc:
            warnings.append(f"{industry.name}权重获取失败：{exc}")
            failures += 1
            if failures >= 3:
                warnings.append("连续 3 个行业权重请求失败，停止本轮获取")
                break
            continue
        failures = 0
        members = [
            (stock, weight, rank)
            for rank, (code, weight) in enumerate(ranked[:TOP_COUNT], 1)
            if (stock := stocks.get(code))
            and (stock.industry_id if industry.level == 1 else stock.industry_l2_id) == industry.id
        ]
        if len(members) < min(TOP_COUNT, len(ranked)):
            warnings.append(f"{industry.name}指数权重前三部分未匹配，保留源名次，不递补")
        if not members:
            warnings.append(f"{industry.name}权重成分与当前上市行业归属未匹配")
            continue
        fetched[industry.id] = members

    fetched_date = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
    imported = {1: 0, 2: 0}
    unavailable_l2 = (
        {
            industry.id
            for industry in industries
            if industry.level == 2 and industry.id not in live_l2
        }
        if live_l2 is not None
        else set()
    )
    with sessions.begin() as session:
        for model, level in ((Representative, 1), (RepresentativeL2, 2)):
            for old in session.scalars(select(model)):
                if (
                    old.industry_id in fetched
                    or old.industry_id in unavailable_l2
                    or not old.source_url.startswith(SOURCE_URL)
                ):
                    session.delete(old)
            session.flush()
            for industry in industries:
                if industry.level != level or industry.id not in fetched:
                    continue
                for stock, weight, rank in fetched[industry.id]:
                    session.add(
                        model(
                            stock_id=stock.id,
                            industry_id=industry.id,
                            position=rank - 1,
                            reason=(
                                f"SW2021 {'一级' if level == 1 else '二级'}行业指数成分权重"
                                f"第 {rank} 位"
                                f"（{weight:.2f}%）；按公开指数权重筛选。"
                            ),
                            source_url=SOURCE_URL + industry.id[:6],
                            reviewed_at=fetched_date,
                        )
                    )
                    imported[level] += 1
    return {
        "level1": imported[1],
        "level2": imported[2],
        "industries_updated": len(fetched),
        "industries_without_index": (
            None
            if live_l2 is None
            else sum(industry.level == 2 and industry.id not in live_l2 for industry in industries)
        ),
        "warnings": warnings,
    }
