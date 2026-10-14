import copy
import json
from pathlib import Path

import pytest
from app.api import database
from app.chain_api import router
from app.chain_models import ChainEdge, ChainImportRun, IndustryChain
from app.chain_service import import_content, publish_content, review_content, validate_content
from app.models import Stock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select


@pytest.fixture
def content():
    value = json.loads(
        (Path(__file__).parents[2] / "config/industry_chains/power-battery.json").read_text()
    )
    # Explicit synthetic securities, never written into the normal database.
    value["id"] = "fixture-chain"
    value["name"] = "测试动力电池"
    a = copy.deepcopy(value["stocks"][3])
    b = copy.deepcopy(a)
    a.update(key="cell-first", ts_code="000001.SZ")
    b.update(key="cell-second", ts_code="000002.SZ")
    value["stocks"] = [a, b]
    value["stocks"][1]["metrics"][0]["revenue"] = 211850917000
    value["stocks"][1]["metrics"][0]["share"] = 50.0
    return value


@pytest.fixture
def api(seeded):
    app = FastAPI()
    app.include_router(router)

    def db():
        with seeded() as s:
            yield s

    app.dependency_overrides[database] = db
    with TestClient(app) as c:
        yield c


def published(factory, doc):
    r = import_content(factory, doc)["revision_id"]
    review_content(factory, r, "pytest", "隔离夹具，非真实资料审核")
    publish_content(factory, r)
    return r


def test_review_required_and_drafts_private(seeded, content, api):
    rid = import_content(seeded, content)["revision_id"]
    assert api.get("/api/industry-chains").json()["total"] == 0
    assert (
        api.get("/api/industry-chains/fixture-chain", params={"revision": rid}).status_code == 404
    )
    with pytest.raises(ValueError):
        publish_content(seeded, rid)
    with pytest.raises(ValueError):
        review_content(seeded, rid, "", "没有核验者")
    review_content(seeded, rid, "pytest", "测试来源与业务核验记录")
    publish_content(seeded, rid)
    assert api.get("/api/industry-chains/fixture-chain").json()["revision_id"] == rid
    with pytest.raises(ValueError):
        review_content(seeded, rid, "other", "不能改写旧版本核验人")


def test_idempotent_import_and_invalid_references_leave_pointer(seeded, content, api):
    rid = published(seeded, content)
    assert import_content(seeded, content)["revision_id"] == rid
    bad = copy.deepcopy(content)
    bad["edges"][0]["target"] = "other-chain-node"
    with pytest.raises(ValueError):
        import_content(seeded, bad)
    with seeded() as s:
        assert s.get(IndustryChain, content["id"]).published_revision == rid
        assert s.scalar(select(ChainImportRun).where(ChainImportRun.state == "failed"))
    bad = copy.deepcopy(content)
    bad["stocks"][0]["evidence"][0]["source_id"] = "invented"
    with pytest.raises(ValueError):
        validate_content(bad)


def test_versions_atomic_and_cross_chain_private(seeded, content, api):
    old = published(seeded, content)
    changed = copy.deepcopy(content)
    changed["nodes"][0]["description"] = "第二版说明"
    new = import_content(seeded, changed)["revision_id"]
    assert api.get("/api/industry-chains/fixture-chain").json()["revision_id"] == old
    review_content(seeded, new, "pytest", "独立记录核验变化后的版本")
    publish_content(seeded, new)
    assert api.get("/api/industry-chains/fixture-chain").json()["revision_id"] == new
    assert (
        api.get("/api/industry-chains/fixture-chain", params={"revision": old}).json()["nodes"][0][
            "description"
        ]
        == content["nodes"][0]["description"]
    )
    with seeded.begin() as s:
        s.add(IndustryChain(id="other-chain", name="其他"))
    assert api.get("/api/industry-chains/other-chain", params={"revision": old}).status_code == 404


def test_graph_count_and_filtered_stock_boundaries(seeded, content, api):
    content["stocks"].append(
        {**copy.deepcopy(content["stocks"][0]), "key": "pack-first", "node": "pack"}
    )
    content["stocks"].append(
        {**copy.deepcopy(content["stocks"][0]), "key": "unknown", "ts_code": "999999.SZ"}
    )
    published(seeded, content)
    d = api.get("/api/industry-chains/fixture-chain").json()
    assert d["stock_count"] == 2 and d["unmatched_count"] == 1
    params = {"node_key": "cell", "stage": "全部"}
    assert api.get("/api/industry-chains/fixture-chain/stocks", params=params).json()["total"] == 2
    with seeded.begin() as s:
        s.get(Stock, 1).name = "*ST甲银行"
    r = api.get("/api/industry-chains/fixture-chain/stocks").json()
    assert r["total"] == 1 and r["filtered_count"] == 1
    invalid = api.get(
        "/api/industry-chains/fixture-chain/compare",
        params={"node_key": "cell", "stock_ids": "1,2"},
    ).json()
    assert invalid["invalid_items"][0]["id"] == 1 and not invalid["comparable"]


def test_sort_pagination_membership_conjunction_and_comparison(seeded, content, api):
    published(seeded, content)
    p = "/api/industry-chains/fixture-chain"
    rows = api.get(
        p + "/stocks", params={"node_key": "cell", "page_size": 1, "sort": "pct_asc"}
    ).json()
    assert rows["total"] == 2 and rows["items"][0]["id"] == 2
    assert api.get(p + "/stocks", params={"node_key": "missing"}).status_code == 404
    assert api.get(p + "/stocks", params={"sort": "invented"}).status_code == 422
    r = api.get(p + "/compare", params={"node_key": "cell", "stock_ids": "1,2"}).json()
    assert r["comparable"] and r["period"] == "2025-FY"
    for ids in ("1", "1,1", "1,2,3,4,5", "-1,2", "abc,2"):
        assert (
            api.get(p + "/compare", params={"node_key": "cell", "stock_ids": ids}).status_code
            == 422
        )
    assert api.get(p + "/compare", params={"node_key": "pack", "stock_ids": "1,2"}).json()[
        "invalid_items"
    ]


def test_security_dates_and_financial_denominator(content):
    for mutation in ("url", "ratio", "date", "duplicate"):
        d = copy.deepcopy(content)
        if mutation == "url":
            d["sources"][0]["url"] = "javascript:alert(1)"
        if mutation == "ratio":
            d["stocks"][0]["metrics"][0]["denominator"] = None
        if mutation == "date":
            d["sources"][0]["retrieved_on"] = "2099-01-01"
        if mutation == "duplicate":
            d["nodes"].append(d["nodes"][0])
        with pytest.raises(ValueError):
            validate_content(d)


def test_real_bundles_validate():
    for p in (Path(__file__).parents[2] / "config/industry_chains").glob("*.json"):
        doc = validate_content(json.loads(p.read_text()))
        assert len(doc["nodes"]) >= 7 and len(doc["sources"]) >= 5
        for n in doc["nodes"]:
            assert n["analyses"]


def test_db_prevents_cross_revision_edges(seeded, content):
    from sqlalchemy.exc import IntegrityError

    rid = published(seeded, content)
    with pytest.raises(IntegrityError):
        with seeded.begin() as s:
            s.add(
                ChainEdge(
                    revision_id=rid, key="bad-endpoint", source="other", target="cell", payload={}
                )
            )


def test_publish_failure_rolls_back_pointer(seeded, content):
    from app.chain_models import ChainRevision
    from sqlalchemy import event

    old = published(seeded, content)
    changed = copy.deepcopy(content)
    changed["summary"] = "另一版本的行业摘要"
    rid = import_content(seeded, changed)["revision_id"]
    review_content(seeded, rid, "pytest", "发布失败注入前的独立核验")

    def fail(_session):
        raise RuntimeError("模拟提交故障")

    event.listen(seeded.class_, "before_commit", fail)
    try:
        with pytest.raises(RuntimeError):
            publish_content(seeded, rid)
    finally:
        event.remove(seeded.class_, "before_commit", fail)
    with seeded() as s:
        assert s.get(IndustryChain, content["id"]).published_revision == old
        assert s.get(ChainRevision, rid).state == "reviewed"


def test_report_period_order_and_currency_mismatch(seeded, content, api):
    for link in content["stocks"]:
        metric = copy.deepcopy(link["metrics"][0])
        metric["period"] = "2025-H1"
        link["metrics"].append(metric)
    published(seeded, content)
    params = {"node_key": "cell", "stock_ids": "1,2"}
    r = api.get("/api/industry-chains/fixture-chain/compare", params=params).json()
    assert r["period"] == "2025-FY"
    assert (
        api.get(
            "/api/industry-chains/fixture-chain/compare", params={**params, "period": "2024-FY"}
        ).status_code
        == 422
    )
    content["stocks"][1]["metrics"][0]["currency"] = "USD"
    published(seeded, content)
    assert not api.get("/api/industry-chains/fixture-chain/compare", params=params).json()[
        "comparable"
    ]
