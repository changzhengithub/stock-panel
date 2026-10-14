"""Isolated synthetic browser fixture. Never writes the user's market database."""

import os
import tempfile
from pathlib import Path

os.environ["REALTIME_QUOTES"] = "0"
os.environ["FUND_FLOW_ENABLED"] = "0"
os.environ["CHAIN_AUTO_UPDATE"] = "0"

os.environ["STOCK_DB_PATH"] = str(
    Path(tempfile.mkdtemp(prefix="stock-panel-e2e-")) / "fixture.sqlite3"
)
from app.db import Session, migrate
from app.models import (
    Calendar,
    Concept,
    ConceptMember,
    Factor,
    Industry,
    IndustrySnapshot,
    Publication,
    Quote,
    Representative,
    RepresentativeL2,
    Stock,
)

migrate()
with Session.begin() as s:
    s.add_all(
        [
            Industry(id="bank", name="银行"),
            Industry(id="tech", name="电子"),
            Industry(id="unclassified", name="未分类"),
            Industry(id="bank_l2", name="银行细分测试", level=2, parent_id="bank"),
            Industry(id="tech_l2", name="电子细分测试", level=2, parent_id="tech"),
        ]
    )
    s.add_all(
        Industry(id=f"fixture-l2-{i}", name=f"测试细分{i}", level=2, parent_id="tech")
        for i in range(132)
    )
    s.add(
        IndustrySnapshot(
            id=1,
            source="浏览器隔离测试",
            fetched_at="2026-01-05T16:00:00+08:00",
            classified_count=56,
            stock_count=56,
        )
    )
    s.flush()
    for i in range(1, 57):
        exchange, board, suffix = (
            ("SSE", "科创板", "SH")
            if i == 3
            else ("BSE", "北交所", "BJ")
            if i == 4
            else ("SZSE", "深市主板", "SZ")
        )
        s.add(
            Stock(
                id=i,
                ts_code=f"{i:06d}.{suffix}",
                symbol=f"{i:06d}",
                name=["测试甲银行", "测试乙银行", "测试电子公司"][min(i - 1, 2)]
                + (str(i) if i > 3 else ""),
                exchange=exchange,
                board=board,
                industry_id="bank" if i < 3 else "tech",
                industry_l2_id="bank_l2" if i < 3 else None if i == 4 else "tech_l2",
                list_date="20200101",
                fullname="浏览器测试专用公司（非真实数据）",
                main_business="用于验证浏览流程的隔离数据",
                introduction="此数据只存在于临时测试数据库。",
            )
        )
    s.flush()
    s.add(
        Concept(
            id="BK1234",
            name="固态电池",
            source="浏览器隔离测试",
            fetched_at="2026-01-05T16:00:00+08:00",
        )
    )
    s.add(
        Concept(
            id="BK5678",
            name="养老概念",
            source="浏览器隔离测试",
            fetched_at="2026-01-05T16:00:00+08:00",
        )
    )
    s.add_all(
        [
            ConceptMember(concept_id="BK1234", stock_id=1),
            ConceptMember(concept_id="BK1234", stock_id=3),
            ConceptMember(concept_id="BK5678", stock_id=2),
        ]
    )
    for i in range(1, 57):
        for day, factor, close in [("20260102", 1.0, 20.0), ("20260105", 2.0, 11.0)]:
            s.add(
                Quote(
                    stock_id=i,
                    trade_date=day,
                    open=close - 0.5,
                    high=close + 0.6,
                    low=close - 0.8,
                    close=close,
                    volume=1000 + i * 10,
                    pct_chg=3 - i / 10,
                    amount=123456789,
                    market_cap=9876543210,
                    float_market_cap=6543210000,
                    turnover_rate=2.48,
                    pe_ratio=18.62,
                    pe_basis="TTM",
                    pb_ratio=1.36,
                    total_shares=1000000000,
                    float_shares=660000000,
                    status="trading",
                )
            )
            s.add(Factor(stock_id=i, trade_date=day, value=factor))
    for i in (1, 2, 3):
        s.add(
            Representative(
                stock_id=i,
                industry_id="bank" if i < 3 else "tech",
                position=i,
                reason="浏览器测试：行业代表性说明。",
                source_url="https://example.org",
                reviewed_at="2026-01-05",
            )
        )
    s.add(
        RepresentativeL2(
            stock_id=1,
            industry_id="bank_l2",
            position=0,
            reason="浏览器测试：二级行业代表性说明。",
            source_url="https://example.org",
            reviewed_at="2026-01-05",
        )
    )
    for day in ("20260102", "20260105"):
        s.add(Calendar(exchange="SSE", date=day, is_open=True, source="test"))
        s.add(Calendar(exchange="SZSE", date=day, is_open=True, source="test"))
        s.add(Publication(trade_date=day, stock_count=56))
from app.fund_flow import publish, scope

for kind in ("concept", "industry"):
    for period, multiplier in (("today", 1), ("5d", 2), ("10d", 3)):
        rows = [
            dict(
                code=f"BK{9000 + i}",
                name=("测试热门概念" if kind == "concept" else "测试资金行业") + str(i),
                net_amount=(10 - i) * 10000000 * multiplier if i != 30 else None,
                net_rate=2.5 - i / 10,
                pct_change=3 - i / 10,
                extra_large=40000000,
                large=60000000,
                medium=-20000000,
                small=-80000000,
                lead_stock="测试甲银行",
                lead_code="000001",
                trade_date="20260105",
                source_as_of="2026-01-05T15:30:00+08:00",
            )
            for i in range(35)
        ]
        data = dict(
            rows=rows,
            total=len(rows),
            source="浏览器隔离资金测试",
            trade_date="20260105",
            source_as_of="2026-01-05T15:30:00+08:00",
            period=period,
        )
        publish(Session, scope(kind, period), kind, data)
        for code in ("BK9000", "BK9001"):
            members = [
                dict(
                    **{k: v for k, v in rows[0].items() if k not in ("code", "name", "net_amount")},
                    code=f"{i:06d}",
                    ts_code=f"{i:06d}.SZ",
                    name="测试甲银行" if i == 1 else "测试乙银行",
                    net_amount=100000000 / i,
                    price=11,
                )
                for i in (1, 2)
            ]
            publish(
                Session,
                scope(kind, period, code, "stocks"),
                kind,
                {**data, "rows": members, "total": 2},
                code,
                "stocks",
            )
    for code in ("BK9000", "BK9001"):
        history = [
            dict(
                trade_date=day,
                net_amount=100000000 if day == "20260105" else -50000000,
                net_rate=2.5,
                provisional=False,
            )
            for day in ("20260102", "20260105")
        ]
        publish(
            Session,
            scope(kind, "daily", code, "history"),
            kind,
            {**data, "rows": history, "total": 2, "period": "daily"},
            code,
            "history",
        )

# Industry-chain fixture uses the same isolated securities and real API contract.
import json
from app.chain_service import import_content, review_content, publish_content
fixture_chain=json.loads((Path(__file__).parents[2]/"config/industry_chains/power-battery.json").read_text())
fixture_chain["id"]="fixture-chain"
fixture_chain["name"]="测试动力电池"
fixture_chain["aliases"]=["电池","新能源","donglidianchi"]
fixture_chain["industry_ids"]=["tech","tech_l2"]
fixture_chain["change_note"]="隔离测试夹具，非真实公司归属。"
for link in fixture_chain["stocks"]:
    link["ts_code"] = "000001.SZ" if link["node"]=="cell" and link["ts_code"]=="300750.SZ" else "000002.SZ" if link["node"]=="cell" else "000003.SH"
rid=import_content(Session,fixture_chain)["revision_id"]
review_content(Session,rid,"浏览器测试夹具","隔离数据库的合成股票映射，仅用于浏览器自动化。")
publish_content(Session,rid)

# A separately labelled synthetic vendor baseline exercises coverage and candidate semantics.
import copy
baseline=copy.deepcopy(fixture_chain)
baseline.update(id="fixture-medical", name="测试医疗器械", aliases=["医疗器械","医疗设备"], coverage_level="baseline", industry_level=2, parent_industry_id="tech", industry_ids=["tech_l2"], scope="浏览器隔离基线，仅合成数据。")
node=next(n for n in baseline["nodes"] if n["key"]=="cell")
node.update(name="诊断产品",assertion_kind="分析框架")
baseline["nodes"]=[node];baseline["edges"]=[]
baseline["stocks"]=[l for l in baseline["stocks"] if l["node"]=="cell"]
for link in baseline["stocks"]:
    link.update(mapping_status="业务词匹配",participation="待核实",operating_stage="未知",leaders=[],business="合成诊断业务，非真实公司结论")
    link["company_analysis"]=["测试业务词关联，需核对实际产品。", "年度与半年度不能直接计算同比，不能把收入占比当成市场份额。"]
    for metric in link["metrics"]:metric["verification"]="数据商汇总待核验"
rid=import_content(Session,baseline)["revision_id"]
review_content(Session,rid,"浏览器测试夹具","合成汇总数据，仅验证基线状态，不作为实际业务核验。")
publish_content(Session,rid)

import uvicorn

uvicorn.run("app.main:app", host="127.0.0.1", port=8011, log_level="warning")
