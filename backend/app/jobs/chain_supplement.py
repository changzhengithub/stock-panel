"""Build all SW industry baselines from explicit sector recipes and source snapshots.

Business matches remain candidates. This command validates drafts; publication remains explicit.
"""

import csv
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.business_analysis import (
    assert_rule_coverage,
    audit_analysis,
    enrich_operating_analysis,
    explain_company,
)
from app.chain_service import import_content, validate_content
from app.jobs.business_collection import snapshots
from app.models import Industry, Stock
from app.settings import ROOT
from app.universe import visible_stock

CLASS_URL = "https://www.stats.gov.cn/xxgk/tjbz/gjtjbz/202008/P020200811608157848094.pdf"
CLASS_HASH = "94f0c6de72a0a7d3fd736843f42abfd830f176e0a7956a27c837c1fbd65a1655"
CLASS_NOTE = "国民经济行业分类注释用于理解经营活动边界；节点组织和影响关系是产品分析框架，不代表来源确认了具体供应链交易。"
# These terms describe generic activities or customer industries and cannot establish node membership.
GENERIC = {
    "工业",
    "设备",
    "制造",
    "消费",
    "企业",
    "服务",
    "投资",
    "贸易",
    "软件",
    "电子",
    "能源",
    "建筑",
    "金属",
    "农业",
    "医疗",
    "金融",
    "银行",
    "汽车",
    "食品",
    "化工",
    "电力",
    "物流",
    "通信",
    "材料",
    "机械",
    "零售",
    "出版",
    "游戏",
    "保险",
    "教育",
    "旅游",
    "传媒",
    "家居",
    "煤炭",
    "环保",
    "钢材",
    "医疗器械",
    "原油",
    "天然气",
    "铜",
    "铝",
    "锂",
    "镍",
    "钴",
    "纸",
    "禽",
    "乳品",
    "影视",
    "运输",
    "研发",
    "煤",
    "资本",
    "存款",
    "广告",
    "包装",
    "纤维",
    "工艺",
}


def recipes():
    root = ROOT / "config/industry_models"
    return {
        name: {
            r["行业"]: r for r in csv.DictReader((root / (name + ".tsv")).open(), delimiter="\t")
        }
        for name in ("sectors", "subindustries")
    }


def parts(value):
    return [(v.split(":")[0], v.split(":")[1].split(",")) for v in value.split("/")]


def product_metrics(snapshot, keywords):
    found = []
    for f in snapshot["financials"]:
        if str(f["MAINOP_TYPE"]) != "2" or not any(k in f["ITEM_NAME"] for k in keywords):
            continue
        revenue = f.get("MAIN_BUSINESS_INCOME")
        total = f.get("TOTAL_BUSINESS_INCOME")
        ratio = f.get("MBI_RATIO")
        # Only report a share when source total and ratio agree. Do not infer a missing denominator.
        share = (
            round(100 * revenue / total, 8)
            if revenue is not None
            and revenue >= 0
            and total
            and total > 0
            and ratio is not None
            and abs(revenue / total - ratio) < 0.0005
            and revenue <= total
            else None
        )
        period = f["REPORT_DATE"][:4] + ("-FY" if "-12-31" in f["REPORT_DATE"] else "-H1")
        if revenue is None or revenue < 0:
            continue
        found.append(
            dict(
                period=period,
                disclosed_on=None,
                subject=f["ITEM_NAME"],
                basis="数据商按产品汇总：" + f["ITEM_NAME"],
                currency="CNY",
                revenue=revenue,
                denominator=total if share is not None else None,
                share=share,
                missing_reason="",
                verification="数据商汇总待核验",
                evidence=[],
            )
        )
    return found


def company_source(stock, snap, acquired):
    return dict(
        id="company-" + stock.ts_code.lower().replace(".", "-"),
        title=stock.name + " · 东方财富主营业务与分部财务汇总",
        url="https://datacenter.eastmoney.com/securities/api/data/v1/get?"
        + urlencode(
            dict(
                reportName="RPT_F10_ORG_BASICINFO",
                columns="SECUCODE,MAIN_BUSINESS,ORG_PROFIE",
                filter=f'(SECUCODE="{stock.ts_code}")',
                pageSize=1,
                pageNumber=1,
            )
        ),
        retrieved_on=acquired,
        category="vendor",
        snapshot_hash=snap.content_hash,
    )


def build_document(industry, all_industries, stocks, facts, specs):
    parent = all_industries[industry.parent_id] if industry.parent_id else industry
    sector = specs["sectors"][parent.name]
    definition = specs["subindustries"][industry.name] if industry.level == 2 else sector
    acquired = max(
        datetime.fromisoformat(f.collected_at)
        .astimezone(ZoneInfo("Asia/Shanghai"))
        .date()
        .isoformat()
        for f in facts.values()
    )
    nodespec = []
    if industry.level == 2:
        core = parts(definition["核心节点与匹配词"])
    else:
        core = [
            (
                child.name,
                [
                    child.name.replace("Ⅱ", ""),
                    *[
                        word
                        for _, words in parts(
                            specs["subindustries"][child.name]["核心节点与匹配词"]
                        )
                        for word in words
                    ],
                ],
            )
            for child in all_industries.values()
            if child.parent_id == industry.id
        ]
    # Central nodes come first for initial selection; graph columns still express upstream/downstream.
    for n, words in core:
        nodespec.append((n, words, 1, "core"))
    for n, words in parts(definition["上游要素"]):
        nodespec.append((n, words, 0, "input"))
    for n, words in parts(definition["下游场景"]):
        nodespec.append((n, words, 2, "output"))
    indicator = definition.get("关键指标", sector["核心观察指标"])
    sources = [
        dict(
            id="activity-definitions",
            title="国民经济行业分类注释 · 经营活动范围",
            url=CLASS_URL,
            retrieved_on=acquired,
            category="framework",
            snapshot_hash=CLASS_HASH,
        )
    ]
    refs = [
        dict(
            source_id="activity-definitions",
            locator=parent.name + "相关经营活动定义；节点与关系为分析整理",
            summary=CLASS_NOTE,
        )
    ]
    nodes = []
    edges = []
    links = []
    source_ids = set()
    for i, (name, words, column, role) in enumerate(nodespec):
        key = "n" + str(i)
        stage = (
            "制造"
            if sector["业务模型"] in ("production", "resource") and role == "core"
            else (
                "材料"
                if role == "input" and sector["业务模型"] == "production"
                else ("应用" if role == "output" else "服务")
            )
        )
        node = dict(
            key=key,
            name=name,
            stage=stage,
            column=column,
            order=i,
            assertion_kind="分析框架",
            variable=indicator,
            description=f"{name}在{industry.name}业务框架中承担"
            + {"core": "产品或服务交付", "input": "投入与支持", "output": "需求或应用"}[role]
            + "作用。各公司的适用范围以实际业务资料为准。",
            gap="结构为行业分析框架；公司业务词匹配需核对原始公告与经营主体。",
            evidence=refs,
            analyses=[
                dict(
                    id="transmission",
                    trigger={
                        "core": "产品需求与业务结构变化",
                        "input": "投入价格或供应能力变化",
                        "output": "客户需求与投资预算变化",
                    }[role],
                    target=industry.name,
                    direction="混合",
                    mechanism={
                        "core": "产品或服务的需求变化影响订单、收入与资源利用效率；需结合价格、成本和回款判断利润变化。",
                        "input": "投入价格上涨或交付受限可能挤压成本与交付能力；拥有相应资源或技术能力的企业也可能获益。",
                        "output": "客户采购、消费或资本开支变化影响需求；真实收入还取决于签约、交付、验收和支付。",
                    }[role],
                    conditions=sector["传导条件"],
                    horizon="取决于合同、库存和交付周期；按最近披露的季度与年度数据验证。",
                    indicators=indicator.split("、"),
                    kind="分析判断",
                    evidence=refs,
                )
            ],
        )
        for stock in stocks:
            f = facts.get(stock.ts_code)
            if not f or not f.payload.get("profile"):
                continue
            p = f.payload["profile"]
            main = p.get("MAIN_BUSINESS") or ""
            classified = (
                stock.industry_l2_id == industry.id
                if industry.level == 2
                else stock.industry_id == industry.id
            )
            same_node = industry.level == 1 and any(
                child.name == name and child.id == stock.industry_l2_id
                for child in all_industries.values()
            )
            metrics = product_metrics(
                f.payload, [w for w in words if w not in GENERIC and len(w) >= 2]
            )
            strong = [
                w
                for w in words
                if (role == "core" and classified or w not in GENERIC)
                and len(w) >= (1 if role == "core" and classified else 2)
            ]
            matched = any(w in main for w in strong) or bool(metrics)
            if role == "core":
                # Classified members always have a truthful entry; they are not assumed verified node members.
                chosen = (
                    classified
                    and (same_node or industry.level == 2 and matched)
                    or (
                        industry.level == 2
                        and sector["业务模型"] in ("production", "resource")
                        and bool(metrics)
                    )
                )
            else:
                chosen = matched
            if not chosen:
                continue
            src = company_source(stock, f, acquired)
            sid = src["id"]
            if sid not in source_ids:
                sources.append(src)
                source_ids.add(sid)
            evidence = [
                dict(
                    source_id=sid,
                    locator="MAIN_BUSINESS 字段；"
                    + stock.ts_code
                    + "；快照 "
                    + f.content_hash[:16],
                    summary="主营业务：" + main[:260] if main else "源接口未给出主营业务说明",
                )
            ]
            for m in metrics:
                m["evidence"] = [
                    dict(
                        source_id=sid,
                        locator=m["period"] + " 产品分部：" + m["subject"] + "；原始披露日未采集",
                        summary="东方财富汇总的分部收入；需核对原始公告的主体、币种和分部边界，不能据此确认节点规模龙头。",
                    )
                ]
            status = "业务词匹配" if matched else "分类候选"
            matched_terms = [
                w
                for w in strong
                if w.lower() in main.lower()
                or any(w.lower() in m["subject"].lower() for m in metrics)
            ]
            links.append(
                dict(
                    key=key + "-" + stock.ts_code.lower().replace(".", "-"),
                    node=key,
                    ts_code=stock.ts_code,
                    subject="上市公司业务汇总；经营主体待核对",
                    business=main[:320],
                    participation="待核实",
                    operating_stage="未知",
                    mapping_status=status,
                    financial_status="已采集匹配分部，待原始公告核验"
                    if metrics
                    else (
                        "已采集财务，但未匹配该节点产品分部"
                        if f.payload["financials"]
                        else "目标报告期数据源缺失"
                    ),
                    evidence=evidence,
                    metrics=metrics,
                    leaders=[],
                )
            )
            links[-1]["company_analysis"] = explain_company(links[-1], matched_terms)
        nodes.append(node)
    mapped_core = {
        x["ts_code"]
        for x in links
        if any(n["key"] == x["node"] and n["column"] == 1 for n in nodes)
    }
    unassigned = [
        x
        for x in stocks
        if (x.industry_l2_id if industry.level == 2 else x.industry_id) == industry.id
        and x.ts_code not in mapped_core
    ]
    if unassigned:
        nodes.append(
            dict(
                key="unassigned",
                name="行业公司（节点待确认）",
                stage="服务",
                column=1,
                order=len(nodes),
                main=False,
                assertion_kind="分析框架",
                variable="主营产品与经营主体核对",
                description="以下公司属于该行业分类，尚未取得足以定位具体业务节点的资料。分类归属只提供研究候选，不确认其参与任一上下游环节。",
                gap="原始公告和实际产品需进一步核验。",
                evidence=refs,
                analyses=[],
            )
        )
        for stock in unassigned:
            snap = facts.get(stock.ts_code)
            if not snap or not snap.payload.get("profile"):
                continue
            src = company_source(stock, snap, acquired)
            if src["id"] not in source_ids:
                sources.append(src)
                source_ids.add(src["id"])
            main = snap.payload["profile"].get("MAIN_BUSINESS") or "源接口未给出主营业务"
            links.append(
                dict(
                    key="unassigned-" + stock.ts_code.lower().replace(".", "-"),
                    node="unassigned",
                    ts_code=stock.ts_code,
                    subject="经营主体待核对",
                    business=main[:320],
                    participation="待核实",
                    operating_stage="未知",
                    mapping_status="分类候选",
                    financial_status="已采集财务，但未确认节点口径"
                    if snap.payload["financials"]
                    else "目标报告期数据源缺失",
                    evidence=[
                        dict(
                            source_id=src["id"],
                            locator="MAIN_BUSINESS 字段；分类仅作为候选",
                            summary="主营业务：" + main[:260],
                        )
                    ],
                    metrics=[],
                    leaders=[],
                )
            )
    for link in links:
        if not link.get("company_analysis"):
            link["company_analysis"] = explain_company(link, [])
    corekeys = [n["key"] for n in nodes if n["column"] == 1 and n["key"] != "unassigned"]
    for n in nodes:
        if n["column"] == 1 or n["key"] == "unassigned":
            continue
        for corekey in corekeys:
            a, b = (n["key"], corekey) if n["column"] == 0 else (corekey, n["key"])
            edges.append(
                dict(
                    key=a + "-" + b,
                    source=a,
                    target=b,
                    kind="供给",
                    assertion_kind="分析判断",
                    description=f"{next(x['name'] for x in nodes if x['key'] == a)}提供投入或服务，连接{next(x['name'] for x in nodes if x['key'] == b)}的经营需求。",
                    conditions=sector["传导条件"]
                    + "这是行业层面可能的业务路径，未确认列表中公司之间存在交易。",
                    evidence=refs,
                )
            )
            edges.append(
                dict(
                    key=b + "-" + a + "-demand",
                    source=b,
                    target=a,
                    kind="需求反馈",
                    assertion_kind="分析判断",
                    description="需求、采购预算或使用强度变化向供给环节反馈，影响订单与资源利用率。",
                    conditions=sector["传导条件"],
                    evidence=refs,
                )
            )
    return validate_content(
        dict(
            id="sw-" + industry.id.split(".")[0],
            name=industry.name,
            aliases=[industry.name.replace("Ⅱ", "")],
            industry_ids=[industry.id],
            coverage_level="baseline",
            business_model=sector["业务模型"],
            industry_level=industry.level,
            parent_industry_id=industry.parent_id,
            scope=(
                "一级行业概览，包含全部二级行业业务分支。"
                if industry.level == 1
                else "二级行业业务框架。"
            )
            + "公司数据为公开数据商快照，节点匹配待核验。",
            summary=f"{industry.name}从{definition['上游要素'].replace(':', '（').split('/')[0].split('（')[0]}等要素进入核心经营活动，再连接"
            + "、".join(n for n, _ in parts(definition["下游场景"]))
            + "。结构解释为分析判断。",
            demand="、".join(n for n, _ in parts(definition["下游场景"]))
            + "的采购、消费或业务使用需求。",
            focus=indicator.split("、"),
            content_as_of=acquired,
            change_note="全行业基线：真实业务与分部数据快照、显式行业框架、候选关联；未逐份人工核验公告。",
            sources=sources,
            nodes=nodes,
            edges=edges,
            stocks=links,
            gaps=[
                "基线覆盖不等于研究核验完成。节点关系为条件分析，未证实企业间交易。",
                "业务词匹配和分类候选需核对经营主体、实际产品、业务阶段与原始公告。",
                "分部收入来自数据商，披露日未采集；行业份额、技术领先及同口径节点龙头依据仍需补证。",
            ],
        )
    )


def add_verified_facts(doc):
    patches = json.loads((ROOT / "config/industry_models/verified_facts.json").read_text())
    patch = patches.get(doc["id"])
    if not patch:
        return doc
    source = patch["source"]
    # Regenerating a document is not reacquiring or re-verifying an original announcement.
    doc["sources"].append(source.copy())
    for confirmed in patch["links"]:
        evidence = confirmed["evidence"]
        node = next(n for n in doc["nodes"] if n["key"] == confirmed["node"])
        node["evidence"].extend(evidence)
        existing = next(
            (
                link
                for link in doc["stocks"]
                if link["node"] == confirmed["node"] and link["ts_code"] == confirmed["ts_code"]
            ),
            None,
        )
        if existing:
            existing.update(
                {
                    k: v
                    for k, v in confirmed.items()
                    if k not in ("metrics", "leaders", "evidence", "key")
                }
            )
            existing["metrics"].extend(confirmed["metrics"])
            existing["leaders"].extend(confirmed["leaders"])
            existing["evidence"].extend(evidence)
        else:
            doc["stocks"].append(confirmed.copy())
    doc["change_note"] += " 已合入单独有来源、范围与报告期的公司事实，核验状态逐项保留。"
    for confirmed in patch["links"]:
        link = next(
            candidate
            for candidate in doc["stocks"]
            if candidate["node"] == confirmed["node"]
            and candidate["ts_code"] == confirmed["ts_code"]
        )
        link["company_analysis"] = explain_company(link, [])
    return validate_content(doc)


def build_all(factory, output=None):
    from app.jobs.industry_chains import chain_lock

    with chain_lock():
        from app.business_analysis import analysis_rules

        analysis_rules.cache_clear()
        with factory() as s:
            industries = {
                x.id: x for x in s.scalars(select(Industry).where(Industry.id != "unclassified"))
            }
            stocks = list(s.scalars(select(Stock).where(visible_stock(s))))
            facts = snapshots(s)
        if not facts:
            raise ValueError("请先采集公司业务资料")
        specs = recipes()
        for level, file in [(1, "sectors"), (2, "subindustries")]:
            expected = {i.name for i in industries.values() if i.level == level}
            if set(specs[file]) != expected:
                raise ValueError(f"{file}行业清单与数据库不一致")
        assert_rule_coverage(specs)
        output = Path(output or ROOT / "data/industry-chain-drafts")
        output.mkdir(parents=True, exist_ok=True)
        result = []
        for industry in sorted(industries.values(), key=lambda x: x.id):
            doc = build_document(industry, industries, stocks, facts, specs)
            doc = validate_content(enrich_operating_analysis(doc, industry, industries))
            doc = add_verified_facts(doc)
            audit = audit_analysis(doc)
            if not audit["passed"]:
                raise ValueError(f"{industry.name}分析未达标：{audit['errors']}")
            (output / (doc["id"] + ".json")).write_text(
                json.dumps(doc, ensure_ascii=False, indent=2)
            )
            r = import_content(factory, doc)
            result.append(
                dict(
                    industry_id=industry.id,
                    name=industry.name,
                    **r,
                    analysis_version=doc["analysis_version"],
                    analysis_audit=audit,
                    nodes=len(doc["nodes"]),
                    links=len(doc["stocks"]),
                    companies=len({x["ts_code"] for x in doc["stocks"]}),
                )
            )
            print(json.dumps(result[-1], ensure_ascii=False), flush=True)
        report = dict(industry_count=len(result), items=result)
        (output / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
        return report


def publish_batch(factory, path, reviewer, note):
    from app.chain_models import ChainRevision
    from app.jobs.industry_chains import chain_lock

    if not reviewer or not note or len(note.strip()) < 8:
        raise ValueError("请注明本批核验人及真实核验范围")
    if not path:
        raise ValueError("请通过 --chain-file 指定批次清单")
    manifest = json.loads(Path(path).read_text())
    rows = manifest["items"]
    if len(rows) != manifest["industry_count"] or len({r["industry_id"] for r in rows}) != len(
        rows
    ):
        raise ValueError("批次行业清单重复或不完整")
    from app.chain_models import IndustryChain
    from app.chain_service import catalog_snapshot
    from app.models import utcnow

    with chain_lock():
        # Publish the whole validated batch atomically. A failure leaves all prior pointers in place.
        with factory.begin() as s:
            expected = set(s.scalars(select(Industry.id).where(Industry.id != "unclassified")))
            if {r["industry_id"] for r in rows} != expected:
                raise ValueError("批次未覆盖全部行业")
            revisions = []
            for row in rows:
                r = s.get(ChainRevision, row["revision_id"])
                if (
                    not r
                    or r.chain_id != "sw-" + row["industry_id"].split(".")[0]
                    or r.payload.get("coverage_level") != "baseline"
                    or r.state not in ("validated", "reviewed", "published")
                ):
                    raise ValueError("批次版本身份或状态不一致")
                validate_content(r.payload)
                if row.get("analysis_version") == 2 and not audit_analysis(r.payload)["passed"]:
                    raise ValueError("全行业专属分析校验失败")
                revisions.append(r)
            for r in revisions:
                if r.state == "validated":
                    r.reviewed_at = utcnow()
                    r.reviewer = reviewer
                    r.review_note = note
                r.state = "published"
                r.published_at = r.published_at or utcnow()
                r.catalog = r.catalog or catalog_snapshot(r.payload)
                c = s.get(IndustryChain, r.chain_id)
                c.published_revision = r.id
                c.name = r.payload["name"]
    return dict(published_count=len(rows), reviewer=reviewer, review_note=note)
