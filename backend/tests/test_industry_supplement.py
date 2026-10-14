import copy
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from app.api import database
from app.business_models import BusinessSnapshot
from app.chain_api import router
from app.chain_coverage import coverage
from app.chain_models import ChainRevision, IndustryChain
from app.chain_service import import_content, publish_content, review_content, search_catalog
from app.jobs.business_collection import BusinessCollector, snapshots
from app.jobs.chain_supplement import product_metrics, publish_batch, recipes
from fastapi import FastAPI
from fastapi.testclient import TestClient


def sample():
    return json.loads(
        (Path(__file__).parents[2] / "config/industry_chains/power-battery.json").read_text()
    )


def make_baseline(factory, industry):
    doc = sample()
    doc.update(id="sw-" + industry, coverage_level="baseline", industry_ids=[industry])
    r = import_content(factory, doc)["revision_id"]
    return doc, r


def test_source_pagination_changes_fail_instead_of_publishing(tmp_path):
    collector = BusinessCollector(tmp_path)
    first = {"response": {"result": {"count": 2, "pages": 2, "data": [{"id": 1}]}}}
    second = {"response": {"result": {"count": 3, "pages": 2, "data": [{"id": 2}]}}}
    collector.page = Mock(side_effect=[first, second])
    with pytest.raises(ValueError, match="分页数量变化"):
        collector.all("report", "filter", "ALL")


def test_baseline_batch_preflight_rolls_back_all_pointers(seeded, tmp_path):
    _, a = make_baseline(seeded, "bank")
    _, b = make_baseline(seeded, "tech")
    path = tmp_path / "manifest.json"
    rows = [
        dict(industry_id="bank", revision_id=a),
        dict(industry_id="tech", revision_id="missing"),
    ]
    path.write_text(json.dumps(dict(industry_count=2, items=rows)))
    with pytest.raises(ValueError, match="不一致"):
        publish_batch(seeded, path, "pytest", "结构校验，业务匹配待核验")
    with seeded() as s:
        assert s.get(IndustryChain, "sw-bank").published_revision is None
        assert s.get(ChainRevision, a).state == "validated"
    rows[-1]["revision_id"] = b
    path.write_text(json.dumps(dict(industry_count=2, items=rows)))
    assert publish_batch(seeded, path, "pytest", "结构校验，业务匹配待核验")["published_count"] == 2
    with seeded() as s:
        assert s.get(IndustryChain, "sw-bank").published_revision == a
        assert s.get(IndustryChain, "sw-tech").published_revision == b
        cards = search_catalog(s)
        assert all(
            c["coverage_level"] == "baseline" and "待核验" in c["review_status"] for c in cards
        )


def test_snapshots_immutable_and_coverage_uses_latest(seeded):
    with seeded.begin() as s:
        s.add(
            BusinessSnapshot(
                ts_code="000001.SZ",
                content_hash="old",
                collected_at="2026-01-01",
                payload={"profile_status": "collected", "financial_status": "source_missing"},
            )
        )
        s.add(
            BusinessSnapshot(
                ts_code="000001.SZ",
                content_hash="new",
                collected_at="2026-02-01",
                payload={"profile_status": "collected", "financial_status": "collected"},
            )
        )
    with seeded() as s:
        assert snapshots(s)["000001.SZ"].content_hash == "new"
        report = coverage(s)
        assert report["company_count"] == 4
        assert report["business_count"] == 1
        assert report["financial_count"] == 1
        assert len(report["items"]) == 2


def test_financial_share_requires_consistent_denominator():
    record = dict(
        MAINOP_TYPE="2",
        ITEM_NAME="电池系统",
        REPORT_DATE="2025-12-31",
        MAIN_BUSINESS_INCOME=10,
        TOTAL_BUSINESS_INCOME=20,
        MBI_RATIO=0.5,
    )
    a = product_metrics({"financials": [record]}, ["电池"])
    assert a[0]["revenue"] == 10 and a[0]["share"] == 50 and a[0]["disclosed_on"] is None
    bad = {**record, "TOTAL_BUSINESS_INCOME": 30}
    assert product_metrics({"financials": [bad]}, ["电池"])[0]["share"] is None
    same = {**record, "MAIN_BUSINESS_INCOME": 20, "MBI_RATIO": 1}
    assert product_metrics({"financials": [same]}, ["电池"])[0]["share"] == 100
    assert not product_metrics({"financials": [{**record, "MAINOP_TYPE": "3"}]}, ["电池"])


def test_baseline_metrics_never_become_financial_rankings(seeded):
    doc = sample()
    doc.update(id="sw-bank", coverage_level="baseline", industry_ids=["bank"])
    link = copy.deepcopy(doc["stocks"][3])
    link.update(ts_code="000001.SZ", key="a")
    other = copy.deepcopy(link)
    other.update(ts_code="000002.SZ", key="b")
    for x in (link, other):
        x["metrics"] = x["metrics"][:1]
        x["metrics"][0]["verification"] = "数据商汇总待核验"
    doc["stocks"] = [link, other]
    r = import_content(seeded, doc)["revision_id"]
    review_content(seeded, r, "pytest", "结构校验，原始资料未核验")
    publish_content(seeded, r)
    app = FastAPI()
    app.include_router(router)

    def db():
        with seeded() as s:
            yield s

    app.dependency_overrides[database] = db
    with TestClient(app) as c:
        result = c.get(
            "/api/industry-chains/sw-bank/compare",
            params={"node_key": link["node"], "stock_ids": "1,2"},
        ).json()
        assert result["comparable"] is False
        assert "不进行财务排名" in result["reason"]
        assert c.get("/api/industry-chains/sw-bank").json()["coverage_level"] == "baseline"


def test_recipes_have_full_explicit_taxonomy_and_service_models():
    spec = recipes()
    assert len(spec["sectors"]) == 31 and len(spec["subindustries"]) == 134
    assert spec["sectors"]["银行"]["业务模型"] == "finance"
    assert "算力" in spec["subindustries"]["软件开发"]["上游要素"]
    assert "体外诊断" in spec["subindustries"]["医疗器械"]["核心节点与匹配词"]


def test_report_periods_follow_disclosure_deadlines():
    from datetime import date

    from app.jobs.business_collection import current_periods

    assert current_periods(date(2026, 1, 15)) == ["2024-12-31", "2025-06-30"]
    assert current_periods(date(2026, 8, 15)) == ["2025-12-31", "2025-06-30"]
    assert current_periods(date(2026, 10, 14)) == ["2025-12-31", "2026-06-30"]


def test_snapshot_http_returns_fixed_content_and_hides_filtered_stock(seeded):
    from app.models import Stock

    payload = {
        "collected_at": "2026-02-01",
        "profile": {"MAIN_BUSINESS": "原始快照的业务文本"},
        "financials": [],
    }
    with seeded.begin() as s:
        s.add(
            BusinessSnapshot(
                ts_code="000001.SZ",
                content_hash="snapshot-hash",
                collected_at="2026-02-01",
                payload=payload,
            )
        )
    app = FastAPI()
    app.include_router(router)

    def db():
        with seeded() as s:
            yield s

    app.dependency_overrides[database] = db
    with TestClient(app) as c:
        response = c.get("/api/industry-chains/business/000001.SZ?snapshot=snapshot-hash")
        assert response.status_code == 200 and response.json()["profile"] == payload["profile"]
        assert c.get("/api/industry-chains/business/000001.SZ?snapshot=unknown").status_code == 404
        with seeded.begin() as s:
            s.get(Stock, 1).list_status = "D"
        assert (
            c.get("/api/industry-chains/business/000001.SZ?snapshot=snapshot-hash").status_code
            == 404
        )
