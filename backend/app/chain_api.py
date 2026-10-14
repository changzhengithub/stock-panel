from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api import database
from app.business_models import BusinessSnapshot  # register snapshot tables before fixtures
from app.chain_service import counts, detail, metadata, resolve_revision, search_catalog, stock_rows
from app.models import Stock
from app.universe import visible_stock

router = APIRouter(prefix="/api/industry-chains", tags=["industry-chains"])
Sort = Literal[
    "default",
    "close_asc",
    "close_desc",
    "pct_asc",
    "pct_desc",
    "market_cap_asc",
    "market_cap_desc",
    "amount_asc",
    "amount_desc",
]
Participation = Literal["全部", "直接经营", "控股子公司", "参股", "其他已披露方式", "待核实"]
Stage = Literal["经营中", "全部", "已形成收入", "已开展经营", "试产", "建设中", "研发中", "未知"]
Leader = Literal["全部", "规模龙头", "份额龙头", "技术领先企业", "代表企业"]


def node_or_404(doc, key):
    n = next((x for x in doc["nodes"] if x["key"] == key), None)
    if not n:
        raise HTTPException(404, "该版本中节点不存在")
    return n


@router.get("")
def catalog(
    q: str = Query("", max_length=80),
    industry_id: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    s: Session = Depends(database),
):
    from app.chain_coverage import coverage, suggestions

    all_cards = search_catalog(s)
    from app.chain_service import filter_catalog

    rows = filter_catalog(all_cards, q, industry_id)
    related = suggestions(
        s, q or (rows[0]["name"] if industry_id and rows else ""), rows, all_cards
    )
    return {
        "items": rows[(page - 1) * page_size : page * page_size],
        "total": len(rows),
        "q": q,
        "recommendations": related,
        "coverage": coverage(s, all_cards),
        "page": page,
        "page_size": page_size,
    }


@router.get("/coverage")
def industry_coverage(s: Session = Depends(database)):
    from app.chain_coverage import coverage

    return coverage(s)


@router.get("/update-status")
def update_status(s: Session = Depends(database)):
    from app.chain_updates import status

    return status(s)


@router.get("/{identity}/version")
def chain_version(identity: str, s: Session = Depends(database)):
    # Only read the small catalogue; polling does not load graph/company payloads.
    from sqlalchemy import select

    from app.chain_models import ChainRevision, IndustryChain

    row = s.execute(
        select(IndustryChain.published_revision, ChainRevision.catalog)
        .join(ChainRevision, IndustryChain.published_revision == ChainRevision.id)
        .where(IndustryChain.id == identity, ChainRevision.state == "published")
    ).first()
    if not row:
        raise HTTPException(404, "内容版本不存在或尚未发布")
    return {"revision_id": row[0], "content_as_of": (row[1] or {}).get("content_as_of")}


@router.get("/business/{ts_code}")
def business_snapshot(ts_code: str, snapshot: str | None = None, s: Session = Depends(database)):
    from sqlalchemy import select

    query = select(BusinessSnapshot).where(BusinessSnapshot.ts_code == ts_code)
    if snapshot:
        query = query.where(BusinessSnapshot.content_hash == snapshot)
    row = s.scalar(query.order_by(BusinessSnapshot.collected_at.desc()).limit(1))
    if not row:
        raise HTTPException(404, "公司业务快照尚未采集")
    if not s.scalar(select(Stock.id).where(Stock.ts_code == ts_code, visible_stock(s))):
        raise HTTPException(404, "股票不在当前浏览范围")
    return {
        **row.payload,
        "ts_code": ts_code,
        "snapshot_hash": row.content_hash,
        "collected_at": row.collected_at,
    }


@router.get("/{identity}")
def chain_detail(identity: str, revision: str | None = None, s: Session = Depends(database)):
    c, r = resolve_revision(s, identity, revision)
    return detail(s, c, r)


@router.get("/{identity}/graph")
def graph(
    identity: str,
    revision: str | None = None,
    view: Literal["simple", "full"] = "simple",
    s: Session = Depends(database),
):
    c, r = resolve_revision(s, identity, revision)
    d = detail(s, c, r)
    nodes = [x for x in d["nodes"] if view == "full" or x["main"]]
    keys = {x["key"] for x in nodes}
    return {
        **metadata(c, r),
        "nodes": nodes,
        "edges": [x for x in d["edges"] if x["source"] in keys and x["target"] in keys],
    }


@router.get("/{identity}/nodes/{node_key}")
def node_detail(
    identity: str, node_key: str, revision: str | None = None, s: Session = Depends(database)
):
    c, r = resolve_revision(s, identity, revision)
    n = node_or_404(r.payload, node_key)
    return {
        **metadata(c, r),
        **n,
        **counts(s, [x for x in r.payload["stocks"] if x["node"] == node_key]),
        "edges": [x for x in r.payload["edges"] if node_key in (x["source"], x["target"])],
    }


@router.get("/{identity}/edges/{edge_key}")
def edge_detail(
    identity: str, edge_key: str, revision: str | None = None, s: Session = Depends(database)
):
    c, r = resolve_revision(s, identity, revision)
    edge = next((x for x in r.payload["edges"] if x["key"] == edge_key), None)
    if not edge:
        raise HTTPException(404, "该版本中关系不存在")
    return {**metadata(c, r), **edge}


@router.get("/{identity}/sources")
def sources(identity: str, revision: str | None = None, s: Session = Depends(database)):
    c, r = resolve_revision(s, identity, revision)
    from sqlalchemy import select

    from app.chain_models import ChainEvidence

    return {
        **metadata(c, r),
        "items": [
            {
                **src,
                "citations": [
                    {"kind": e.target_kind, "key": e.target_key, **e.payload}
                    for e in s.scalars(
                        select(ChainEvidence).where(
                            ChainEvidence.revision_id == r.id, ChainEvidence.source_key == src["id"]
                        )
                    )
                ],
            }
            for src in r.payload["sources"]
        ],
    }


@router.get("/{identity}/stocks")
def stocks(
    identity: str,
    revision: str | None = None,
    node_key: str | None = None,
    q: str = Query("", max_length=80),
    participation: Participation = "全部",
    stage: Stage = "经营中",
    leader: Leader = "全部",
    mapping_status: Literal["全部", "资料核验", "业务词匹配", "分类候选"] = "全部",
    sort: Sort = "default",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    s: Session = Depends(database),
):
    c, r = resolve_revision(s, identity, revision)
    if node_key:
        node_or_404(r.payload, node_key)
    links = [x for x in r.payload["stocks"] if not node_key or x["node"] == node_key]
    rows = stock_rows(s, r.payload, node_key)

    def matches(m):
        return (
            (mapping_status == "全部" or m.get("mapping_status", "资料核验") == mapping_status)
            and (participation == "全部" or m["participation"] == participation)
            and (
                stage == "全部"
                or m["operating_stage"] == stage
                or stage == "经营中"
                and m["operating_stage"] in ("已形成收入", "已开展经营")
            )
            and (leader == "全部" or any(x["kind"] == leader for x in m["leaders"]))
        )

    rows = [
        x
        for x in rows
        if any(matches(m) for m in x["memberships"])
        and (not q or q.lower() in x["name"].lower() or q.lower() in x["ts_code"].lower())
    ]
    rows.sort(
        key=lambda x: (
            not any(m.get("mapping_status", "资料核验") == "资料核验" for m in x["memberships"])
            if r.payload.get("coverage_level") == "baseline"
            else False,
            x["code"],
            x["exchange"],
        )
    )
    if sort != "default":
        field, direction = sort.rsplit("_", 1)
        field = "pct_chg" if field == "pct" else field
        if field == "pct_chg":
            rows = [x for x in rows if x["status"] == "trading" and x[field] is not None]
        sign = -1 if direction == "desc" else 1
        rows.sort(
            key=lambda x: (x[field] is None, sign * (x[field] or 0), x["code"], x["exchange"])
        )
    return {
        **metadata(c, r),
        **counts(s, links),
        "items": rows[(page - 1) * page_size : page * page_size],
        "total": len(rows),
        "page": page,
        "page_size": page_size,
    }


@router.get("/{identity}/compare")
def compare(
    identity: str,
    node_key: str,
    stock_ids: str,
    revision: str | None = None,
    period: str | None = None,
    s: Session = Depends(database),
):
    c, r = resolve_revision(s, identity, revision)
    node_or_404(r.payload, node_key)
    try:
        ids = [int(x) for x in stock_ids.split(",")]
    except ValueError:
        raise HTTPException(422, "股票身份必须为整数") from None
    if len(ids) != len(set(ids)) or not 2 <= len(ids) <= 4 or any(x < 1 for x in ids):
        raise HTTPException(422, "请选择同节点 2～4 家不同公司")
    available = {x["id"]: x for x in stock_rows(s, r.payload, node_key)}
    invalid = [
        {"id": i, "reason": "不属于该版本节点、无法匹配或已被当前股票池过滤"}
        for i in ids
        if i not in available
    ]
    rows = [available[i] for i in ids if i in available]
    periods = [{m["period"] for link in x["memberships"] for m in link["metrics"]} for x in rows]
    common = set.intersection(*periods) if periods and not invalid else set()

    def period_order(value):
        year, suffix = value.split("-", 1)
        return int(year), {"Q1": 1, "H1": 2, "Q2": 2, "Q3": 3, "Q4": 4, "FY": 5}.get(suffix, 0)

    if period is not None and period not in common:
        raise HTTPException(422, "指定报告期不属于各公司共同可用报告期")
    selected = period or max(common, key=period_order, default=None)

    def metrics(x):
        values = [
            m
            for link in x["memberships"]
            for m in link["metrics"]
            if selected and m["period"] == selected
        ]
        return values

    selected_metrics = [metrics(x) for x in rows]
    # Only a single metric of the exact same business basis/currency/period can be compared.
    comparable = bool(
        selected
        and not invalid
        and all(
            len(ms) == 1
            and ms[0]["revenue"] is not None
            and ms[0].get("verification", "原始资料核验") == "原始资料核验"
            for ms in selected_metrics
        )
        and len({(ms[0]["basis"], ms[0]["currency"]) for ms in selected_metrics}) == 1
    )
    return {
        **metadata(c, r),
        "node_key": node_key,
        "items": [{**x, "comparison_metrics": ms} for x, ms in zip(rows, selected_metrics)],
        "invalid_items": invalid,
        "period": selected,
        "common_periods": sorted(common, key=period_order, reverse=True),
        "comparable": comparable,
        "reason": "同报告期、同币种、同业务口径"
        if comparable
        else "缺少共同报告期或同口径分部数据，不进行财务排名。",
        "requested_period": period,
    }
