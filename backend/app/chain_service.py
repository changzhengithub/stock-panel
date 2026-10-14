"""Strict imports, explicit review, atomic publication and current-universe reads."""

import hashlib
import json
from functools import lru_cache
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.chain_models import (
    ChainAnalysis,
    ChainBusinessMetric,
    ChainEdge,
    ChainEvidence,
    ChainImportRun,
    ChainLeaderClaim,
    ChainNode,
    ChainRevision,
    ChainSource,
    ChainStockLink,
    IndustryChain,
)
from app.chain_schemas import ChainDocument
from app.models import CodeAlias, Stock, utcnow
from app.search import spellings
from app.settings import ROOT
from app.universe import visible_stock


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def catalog_snapshot(doc):
    return {
        **{
            k: doc.get(k)
            for k in (
                "name",
                "scope",
                "summary",
                "aliases",
                "industry_ids",
                "content_as_of",
                "coverage_level",
                "business_model",
                "analysis_version",
                "industry_level",
                "parent_industry_id",
            )
        },
        "node_count": len(doc["nodes"]),
        "source_unavailable": sum(x["access_status"] == "unavailable" for x in doc["sources"]),
        "stocks": [{k: x[k] for k in ("ts_code", "leaders")} for x in doc["stocks"]],
        "verified_count": len(
            {
                x["ts_code"]
                for x in doc["stocks"]
                if x.get("mapping_status", "资料核验") == "资料核验"
            }
        ),
    }


def validate_content(value):
    doc = ChainDocument.model_validate(value)
    normalized = doc.model_dump(mode="json")
    if doc.analysis_version >= 2:
        from app.business_analysis import audit_analysis

        audit = audit_analysis(normalized)
        if not audit["passed"]:
            raise ValueError("专属行业分析不完整：" + "；".join(audit["errors"]))
    return normalized


def import_content(factory, value):
    """Record failures separately; an import never changes the published pointer."""
    run_id = uuid4().hex
    input_hash = digest(value)
    chain_id = str(value.get("id", "unknown"))
    try:
        doc = validate_content(value)
        content_hash = digest(doc)
        with factory.begin() as s:
            old = s.scalar(
                select(ChainRevision).where(
                    ChainRevision.chain_id == doc["id"], ChainRevision.content_hash == content_hash
                )
            )
            if old:
                if not old.catalog:
                    old.catalog = catalog_snapshot(old.payload)
                return {"revision_id": old.id, "state": old.state, "unchanged": True}
            chain = s.get(IndustryChain, doc["id"])
            if not chain:
                chain = IndustryChain(id=doc["id"], name=doc["name"])
                s.add(chain)
                s.flush()
            revision = ChainRevision(
                id=uuid4().hex,
                chain_id=chain.id,
                content_hash=content_hash,
                payload=doc,
                catalog=catalog_snapshot(doc),
                state="validated",
            )
            s.add(revision)
            s.flush()
            rid = revision.id
            s.add_all(ChainNode(revision_id=rid, key=x["key"], payload=x) for x in doc["nodes"])
            s.add_all(
                ChainSource(revision_id=rid, key=x["id"], snapshot_hash=digest(x), payload=x)
                for x in doc["sources"]
            )
            s.flush()
            s.add_all(
                ChainEdge(
                    revision_id=rid, key=x["key"], source=x["source"], target=x["target"], payload=x
                )
                for x in doc["edges"]
            )
            s.add_all(
                ChainStockLink(
                    revision_id=rid,
                    key=x["key"],
                    node_key=x["node"],
                    ts_code=x["ts_code"],
                    payload=x,
                )
                for x in doc["stocks"]
            )
            s.flush()

            def evidence(kind, key, refs):
                for i, e in enumerate(refs):
                    s.add(
                        ChainEvidence(
                            revision_id=rid,
                            key=f"{kind}:{key}:{i}",
                            source_key=e["source_id"],
                            target_kind=kind,
                            target_key=key,
                            payload=e,
                        )
                    )

            for n in doc["nodes"]:
                evidence("node", n["key"], n["evidence"])
                for a in n["analyses"]:
                    key = f"{n['key']}:{a['id']}"
                    s.add(ChainAnalysis(revision_id=rid, key=key, node_key=n["key"], payload=a))
                    evidence("analysis", key, a["evidence"])
            for e in doc["edges"]:
                evidence("edge", e["key"], e["evidence"])
            for link in doc["stocks"]:
                evidence("stock", link["key"], link["evidence"])
                for typ, cls, records in (
                    ("metric", ChainBusinessMetric, link["metrics"]),
                    ("leader", ChainLeaderClaim, link["leaders"]),
                ):
                    for i, x in enumerate(records):
                        key = f"{link['key']}:{i}"
                        s.add(cls(revision_id=rid, key=key, link_key=link["key"], payload=x))
                        evidence(typ, key, x["evidence"])
            s.add(
                ChainImportRun(
                    id=run_id,
                    chain_id=chain.id,
                    input_hash=input_hash,
                    revision_id=rid,
                    state="validated",
                    finished_at=utcnow(),
                )
            )
            return {"revision_id": rid, "state": "validated", "unchanged": False}
    except Exception as e:
        with factory.begin() as s:
            s.add(
                ChainImportRun(
                    id=run_id,
                    chain_id=chain_id,
                    input_hash=input_hash,
                    state="failed",
                    finished_at=utcnow(),
                    error=str(e)[:1500],
                )
            )
        raise


def review_content(factory, revision_id, reviewer, note):
    if not reviewer.strip() or len(note.strip()) < 8:
        raise ValueError("需记录核验人及具体资料核验说明")
    with factory.begin() as s:
        r = s.get(ChainRevision, revision_id)
        if not r:
            raise ValueError("内容版本不存在")
        if r.state == "published":
            raise ValueError("已发布版本不可原地修改审核记录")
        validate_content(r.payload)
        r.state = "reviewed"
        r.reviewer = reviewer.strip()
        r.review_note = note.strip()
        r.reviewed_at = utcnow()
    return {"revision_id": revision_id, "state": "reviewed"}


def publish_content(factory, revision_id):
    with factory.begin() as s:
        r = s.get(ChainRevision, revision_id)
        if not r or r.state not in ("reviewed", "published"):
            raise ValueError("仅允许发布已完成资料核验的版本")
        if r.state == "published":
            return {"revision_id": r.id, "state": r.state, "unchanged": True}
        validate_content(r.payload)
        r.state = "published"
        r.published_at = utcnow()
        chain = s.get(IndustryChain, r.chain_id)
        chain.published_revision = r.id
        chain.name = r.payload["name"]
    return {"revision_id": revision_id, "state": "published"}


def resolve_revision(s, chain_id, revision=None):
    chain = s.get(IndustryChain, chain_id)
    if not chain:
        raise HTTPException(404, "产业链不存在或尚未发布")
    r = (
        s.get(ChainRevision, revision or chain.published_revision)
        if (revision or chain.published_revision)
        else None
    )
    if not r or r.chain_id != chain_id or r.state != "published":
        raise HTTPException(404, "内容版本不存在或尚未发布")
    return chain, r


def metadata(chain, r):
    d = r.catalog or catalog_snapshot(r.payload)
    baseline = d.get("coverage_level") == "baseline"
    return {
        "chain_id": chain.id,
        "revision_id": r.id,
        "current_revision_id": chain.published_revision,
        "published_at": r.published_at,
        "content_as_of": d["content_as_of"],
        "reviewed_at": r.reviewed_at,
        "reviewer": r.reviewer,
        "review_note": r.review_note,
        "review_status": (
            "专属经营分析已生成，资料分项核验"
            if (d.get("analysis_version") or 1) >= 2
            else "基线校验完成，业务关联待核验"
        )
        if baseline
        else "资料核验完成",
        "coverage_level": "baseline" if baseline else "curated",
        "industry_level": d.get("industry_level"),
        "parent_industry_id": d.get("parent_industry_id"),
        "industry_ids": d.get("industry_ids", []),
        "verified_count": d.get("verified_count", 0),
        "analysis_version": d.get("analysis_version") or 1,
        "pending_review_count": d.get("source_unavailable", 0),
    }


def mapped_stocks(s, links):
    codes = {x["ts_code"] for x in links}
    direct = {x.ts_code: x.id for x in s.scalars(select(Stock).where(Stock.ts_code.in_(codes)))}
    aliases = {
        x.code: x.stock_id for x in s.scalars(select(CodeAlias).where(CodeAlias.code.in_(codes)))
    }
    return {**aliases, **direct}


def counts(s, links):
    mapping = mapped_stocks(s, links)
    ids = set(mapping.values())
    visible = set(s.scalars(select(Stock.id).where(Stock.id.in_(ids), visible_stock(s))))
    return {
        "registered_count": len(ids)
        + len({x["ts_code"] for x in links if x["ts_code"] not in mapping}),
        "unmatched_count": len({x["ts_code"] for x in links if x["ts_code"] not in mapping}),
        "filtered_count": len(ids - visible),
        "stock_count": len(visible),
        "leader_count": len(
            {
                mapping[x["ts_code"]]
                for x in links
                if mapping.get(x["ts_code"]) in visible
                and any(y["kind"] != "代表企业" for y in x["leaders"])
            }
        ),
    }


def detail(s, chain, r):
    doc = r.payload
    return {
        **doc,
        **metadata(chain, r),
        **counts(s, doc["stocks"]),
        "nodes": [
            {**n, **counts(s, [x for x in doc["stocks"] if x["node"] == n["key"]])}
            for n in doc["nodes"]
        ],
        "stocks": None,
    }


def stock_rows(s, doc, node=None):
    # Reuse the existing stock projection including quote overlay and source semantics.
    from app.api import base_query, item, latest
    from app.chain_updates import last_run, period_end
    from app.jobs.business_collection import collection_periods
    from app.realtime import snapshot_for

    target_period = max(collection_periods())
    run = last_run(s)
    good = last_run(s, success=True) if not run or not run.payload.get("maintenance") else run
    checks = (good.payload.get("maintenance") or {}).get("source_checks", []) if good else []
    pending_sources = {x["url"] for x in checks if x["state"] != "unchanged"}
    pending_ids = {x["id"] for x in doc["sources"] if x["url"] in pending_sources}

    def leader_status(claim):
        if any(e["source_id"] in pending_ids for e in claim["evidence"]):
            return "证据来源待复核，当前地位尚未重新确认"
        if period_end(claim["period"]) < target_period:
            return "历史报告期依据，待最新资料复核"
        return "适用于所列报告期"

    links = [x for x in doc["stocks"] if not node or x["node"] == node]
    mapping = mapped_stocks(s, links)
    live = snapshot_for(s)
    rows = s.execute(
        base_query(latest(s)).where(Stock.id.in_(set(mapping.values())), visible_stock(s))
    ).all()
    result = []
    for raw in rows:
        stock = item(raw, live=live)
        memberships = [
            {
                **x,
                "leaders": [
                    {
                        **claim,
                        "freshness": leader_status(claim),
                    }
                    for claim in x["leaders"]
                ],
            }
            for x in links
            if mapping.get(x["ts_code"]) == stock["id"]
        ]
        result.append(
            {
                **stock,
                "memberships": memberships,
                "nodes": [
                    {"key": n["key"], "name": n["name"]}
                    for n in doc["nodes"]
                    if any(x["node"] == n["key"] for x in memberships)
                ],
            }
        )
    return result


@lru_cache(maxsize=1)
def search_terms():
    return json.loads((ROOT / "config/industry_models/search_terms.json").read_text())


def labels_for(card):
    return [card["name"], card["id"], *card.get("aliases", []), *search_terms().get(card["id"], [])]


def search_catalog(s, q="", industry_id=None):
    from sqlalchemy.orm import defer

    key = q.strip().lower()
    result = []
    direct = {x.ts_code: x.id for x in s.scalars(select(Stock))}
    mapping = {**{x.code: x.stock_id for x in s.scalars(select(CodeAlias))}, **direct}
    visible = set(s.scalars(select(Stock.id).where(visible_stock(s))))
    for chain, r in s.execute(
        select(IndustryChain, ChainRevision)
        .join(ChainRevision, IndustryChain.published_revision == ChainRevision.id)
        .options(defer(ChainRevision.payload))
    ):
        d = r.catalog or catalog_snapshot(r.payload)
        if industry_id and industry_id not in d["industry_ids"]:
            continue
        labels = labels_for({**d, "id": chain.id})
        exact = key in [x.lower() for x in labels]
        if key and not any(key in v.lower() or any(key in p for p in spellings(v)) for v in labels):
            continue
        ids = {mapping[x["ts_code"]] for x in d["stocks"] if x["ts_code"] in mapping}
        missing = {x["ts_code"] for x in d["stocks"] if x["ts_code"] not in mapping}
        leaders = {
            mapping[x["ts_code"]]
            for x in d["stocks"]
            if mapping.get(x["ts_code"]) in visible
            and any(y["kind"] != "代表企业" for y in x["leaders"])
        }
        result.append(
            {
                **metadata(chain, r),
                "id": chain.id,
                "name": d["name"],
                "scope": d["scope"],
                "summary": d["summary"],
                "aliases": d["aliases"],
                "node_count": d["node_count"],
                "stock_count": len(ids & visible),
                "registered_count": len(ids) + len(missing),
                "unmatched_count": len(missing),
                "filtered_count": len(ids - visible),
                "leader_count": len(leaders),
                "match_reason": "名称或别名匹配" if exact else "相关分析范围",
            }
        )
    return sorted(
        result,
        key=lambda x: (
            x["name"] != q,
            x["coverage_level"] != "baseline",
            x["industry_level"] != 1,
            x["id"],
        ),
    )


def filter_catalog(cards, q="", industry_id=None):
    key = q.strip().lower()
    result = []
    for card in cards:
        if industry_id and industry_id not in card["industry_ids"]:
            continue
        labels = labels_for(card)
        if key and not any(
            key in label.lower() or any(key in p for p in spellings(label)) for label in labels
        ):
            continue
        result.append(
            {
                **card,
                "match_reason": "名称或别名匹配"
                if key in [card["name"].lower(), *[a.lower() for a in card["aliases"]]]
                else (
                    "业务主题候选，请确认范围" if key else card.get("match_reason", "相关分析范围")
                ),
            }
        )
    return sorted(
        result,
        key=lambda x: (
            x["name"].lower() != key,
            x["coverage_level"] != "baseline",
            x["industry_level"] != 1,
            x["id"],
        ),
    )
