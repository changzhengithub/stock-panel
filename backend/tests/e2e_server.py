"""Isolated synthetic browser fixture. Never writes the user's market database."""

import os
import tempfile
from pathlib import Path

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
    s.add(IndustrySnapshot(id=1, source="浏览器隔离测试", fetched_at="2026-01-05T16:00:00+08:00", classified_count=56, stock_count=56))
    s.flush()
    for i in range(1, 57):
        exchange, board, suffix = (
            ("SSE", "科创板", "SH") if i == 3
            else ("BSE", "北交所", "BJ") if i == 4
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
    s.add(Concept(id="BK1234", name="固态电池", source="浏览器隔离测试", fetched_at="2026-01-05T16:00:00+08:00"))
    s.add(Concept(id="BK5678", name="养老概念", source="浏览器隔离测试", fetched_at="2026-01-05T16:00:00+08:00"))
    s.add_all([
        ConceptMember(concept_id="BK1234", stock_id=1),
        ConceptMember(concept_id="BK1234", stock_id=3),
        ConceptMember(concept_id="BK5678", stock_id=2),
    ])
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
import uvicorn

uvicorn.run("app.main:app", host="127.0.0.1", port=8011, log_level="warning")
