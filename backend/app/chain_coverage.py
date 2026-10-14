"""Taxonomy coverage and explicit recommendation reasons, independent of publication claims."""

from difflib import SequenceMatcher

from sqlalchemy import select

from app.business_models import BusinessCollection, BusinessSnapshot
from app.chain_service import search_catalog
from app.models import Industry, Stock
from app.search import spellings
from app.universe import visible_stock


def coverage(s, cards=None):
    cards = cards if cards is not None else search_catalog(s)
    run = s.scalar(
        select(BusinessCollection)
        .where(BusinessCollection.state == "complete")
        .order_by(BusinessCollection.started_at.desc())
        .limit(1)
    )
    selected = run.payload.get("snapshot_hashes", {}) if run else {}
    facts = {}
    selected_facts = {}
    for code, content_hash, profile_status, financial_status in s.execute(
        select(
            BusinessSnapshot.ts_code,
            BusinessSnapshot.content_hash,
            BusinessSnapshot.payload["profile_status"].as_string(),
            BusinessSnapshot.payload["financial_status"].as_string(),
        ).order_by(BusinessSnapshot.collected_at, BusinessSnapshot.content_hash)
    ):
        facts[code] = {"profile_status": profile_status, "financial_status": financial_status}
        if selected.get(code) == content_hash:
            selected_facts[code] = facts[code]
    facts.update(selected_facts)
    companies = list(s.scalars(select(Stock).where(visible_stock(s))))
    rows = []
    for i in s.scalars(
        select(Industry).where(Industry.id != "unclassified").order_by(Industry.level, Industry.id)
    ):
        members = [
            x for x in companies if (x.industry_id if i.level == 1 else x.industry_l2_id) == i.id
        ]
        current = [c for c in cards if i.id in c["industry_ids"]]
        rows.append(
            dict(
                id=i.id,
                name=i.name,
                level=i.level,
                parent_id=i.parent_id,
                company_count=len(members),
                business_count=sum(
                    bool(
                        facts.get(x.ts_code)
                        and facts[x.ts_code].get("profile_status") == "collected"
                    )
                    for x in members
                ),
                financial_count=sum(
                    bool(
                        facts.get(x.ts_code)
                        and facts[x.ts_code].get("financial_status") == "collected"
                    )
                    for x in members
                ),
                analysis_ready=any(c.get("analysis_version", 1) >= 2 for c in current),
                status="行业专属分析已生成；资料分项核验"
                if any(c.get("analysis_version", 1) >= 2 for c in current)
                else "有专题核验及行业基线"
                if any(c["coverage_level"] == "curated" for c in current)
                else ("行业基线已收录，关联待核验" if current else "待建立分析框架"),
                chains=[
                    dict(id=c["id"], name=c["name"], coverage_level=c["coverage_level"])
                    for c in current
                ],
            )
        )
    return dict(
        items=rows,
        total=len(rows),
        l1_count=sum(x["level"] == 1 for x in rows),
        l2_count=sum(x["level"] == 2 for x in rows),
        covered_count=sum(bool(x["chains"]) for x in rows),
        analysed_count=sum(x["analysis_ready"] for x in rows),
        company_count=len(companies),
        business_count=sum(
            bool(facts.get(x.ts_code) and facts[x.ts_code].get("profile_status") == "collected")
            for x in companies
        ),
        financial_count=sum(
            bool(facts.get(x.ts_code) and facts[x.ts_code].get("financial_status") == "collected")
            for x in companies
        ),
        collection=run.payload if run else None,
    )


def suggestions(s, q, matches, cards=None):
    if not q.strip():
        return []
    cards = cards if cards is not None else search_catalog(s)
    industries = {x.id: x for x in s.scalars(select(Industry).where(Industry.id != "unclassified"))}
    matchedids = {i for c in matches for i in c["industry_ids"]}
    result = []
    seen = {x["id"] for x in matches}
    for card in cards:
        if card["id"] in seen:
            continue
        reason = None
        for targetid in matchedids:
            target = industries.get(targetid)
            if not target:
                continue
            for otherid in card["industry_ids"]:
                other = industries.get(otherid)
                if not other:
                    continue
                if other.parent_id == target.id:
                    reason = f"{target.name}的二级行业"
                elif target.parent_id == other.id:
                    reason = f"{target.name}的一级行业概览"
                elif target.parent_id and target.parent_id == other.parent_id:
                    reason = "同属" + industries[target.parent_id].name + "，可比较相邻业务"
        if reason:
            result.append({**card, "recommendation_reason": reason})
    if not matches:
        key = q.strip().lower()
        scored = []
        for c in cards:
            score = max(
                SequenceMatcher(None, key, label.lower()).ratio()
                for label in [c["name"], *c.get("aliases", []), *spellings(c["name"])]
            )
            if score >= 0.48:
                scored.append((score, c))
        result = [
            {**c, "recommendation_reason": "名称近似，请确认是否为目标行业"}
            for _, c in sorted(scored, key=lambda x: (-x[0], x[1]["id"]))[:6]
        ]
    return result[:8]
