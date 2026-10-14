import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
from app import chain_updates as updates
from app.api import database
from app.business_analysis import enrich_operating_analysis
from app.business_models import BusinessCollection, BusinessSnapshot, ChainUpdateRun
from app.chain_api import router
from app.chain_models import ChainRevision, IndustryChain
from app.chain_service import import_content, publish_content, review_content, validate_content
from app.jobs import business_collection as acquisition
from app.models import Industry, utcnow
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select


def sample():
    return json.loads(
        (Path(__file__).parents[2] / "config/industry_chains/power-battery.json").read_text()
    )


def build_fixture(factory, output):
    with factory() as s:
        industries = {x.id: x for x in s.scalars(select(Industry))}
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for industry in industries.values():
        doc = sample()
        doc.update(id="sw-" + industry.id, industry_ids=[industry.id], coverage_level="baseline")
        doc["stocks"] = []
        for index, node in enumerate(doc["nodes"]):
            node["column"] = index % 3
        doc = validate_content(
            enrich_operating_analysis(validate_content(doc), industry, industries)
        )
        result = import_content(factory, doc)
        rows.append(
            dict(
                industry_id=industry.id,
                analysis_version=2,
                analysis_audit={"passed": True},
                **result,
            )
        )
    manifest = dict(industry_count=len(rows), items=rows)
    (output / "manifest.json").write_text(json.dumps(manifest))
    return manifest


@pytest.fixture
def pipeline(seeded, monkeypatch, tmp_path):
    collect = Mock(
        return_value=dict(
            periods=["2025-12-31", "2026-06-30"],
            collected_at=utcnow(),
            business_count=4,
            financial_count=4,
        )
    )
    build = Mock(side_effect=build_fixture)
    monkeypatch.setattr(updates, "collect", collect)
    monkeypatch.setattr(updates, "build_all", build)
    monkeypatch.setattr(updates, "model_signature", lambda: "rules-v1")
    monkeypatch.setattr(
        updates,
        "check_maintenance",
        lambda *a, **kw: {"leader_review_count": 0, "source_review_count": 0, "source_checks": []},
    )
    return seeded, tmp_path / "drafts", collect, build


def test_automatic_publication_then_unchanged_has_no_extra_revisions(pipeline):
    factory, output, collect, build = pipeline
    first = updates.update(factory, force=True, output=output)
    assert first["state"] == "published" and first["published_count"] == 2
    with factory() as s:
        assert all(x.published_revision for x in s.scalars(select(IndustryChain)))
        count = s.scalar(select(func.count()).select_from(ChainRevision))
    second = updates.update(factory, force=True, output=output)
    assert second["state"] == "unchanged"
    assert collect.call_count == 2 and build.call_count == 1
    with factory() as s:
        assert s.scalar(select(func.count()).select_from(ChainRevision)) == count
        assert updates.status(s)["last_success_at"]
    assert updates.update(factory, output=output)["state"] == "not_due"
    assert collect.call_count == 2


@pytest.mark.parametrize("failure", ["collect", "build", "validation"])
def test_failed_updates_preserve_all_published_pointers(pipeline, failure, monkeypatch):
    factory, output, collect, build = pipeline
    assert updates.update(factory, force=True, output=output)["state"] == "published"
    with factory() as s:
        before = {x.id: x.published_revision for x in s.scalars(select(IndustryChain))}
    monkeypatch.setattr(updates, "model_signature", lambda: "rules-v2")
    if failure == "collect":
        collect.side_effect = ValueError("来源失败")
    elif failure == "build":
        build.side_effect = ValueError("规则缺失")
    else:
        build.side_effect = lambda f, p: {"items": [{"analysis_version": 1}]}
    result = updates.update(factory, force=True, output=output)
    assert result["state"] == "failed"
    with factory() as s:
        assert {x.id: x.published_revision for x in s.scalars(select(IndustryChain))} == before
        state = updates.status(s)
        assert state["error"] and state["last_success_at"]
        assert datetime.fromisoformat(state["next_check_at"]) > datetime.now(updates.TZ)


def test_rule_change_runs_before_regular_schedule(pipeline, monkeypatch):
    factory, output, collect, build = pipeline
    updates.update(factory, force=True, output=output)
    monkeypatch.setattr(updates, "model_signature", lambda: "rules-v2")
    assert updates.update(factory, output=output)["state"] == "published"
    assert build.call_count == 2


def test_mid_build_rule_edit_does_not_publish(pipeline, monkeypatch):
    factory, output, collect, build = pipeline
    monkeypatch.setattr(updates, "model_signature", Mock(side_effect=["rules-v1", "rules-v2"]))
    assert updates.update(factory, force=True, output=output)["state"] == "failed"
    with factory() as s:
        assert all(x.published_revision is None for x in s.scalars(select(IndustryChain)))


def test_restart_marks_orphan_and_recovers(pipeline):
    factory, output, _, _ = pipeline
    with factory.begin() as s:
        s.add(
            ChainUpdateRun(
                id="orphan", state="running", started_at="2020-01-01T00:00:00+00:00", payload={}
            )
        )
    assert updates.update(factory, output=output)["state"] == "published"
    with factory() as s:
        assert s.get(ChainUpdateRun, "orphan").state == "interrupted"


def test_busy_lock_does_not_start_collection(pipeline, monkeypatch):
    from contextlib import contextmanager

    factory, output, collect, _ = pipeline

    @contextmanager
    def busy():
        raise BlockingIOError()
        yield

    monkeypatch.setattr(updates, "chain_lock", busy)
    assert updates.update(factory, force=True, output=output)["state"] == "busy"
    collect.assert_not_called()


def test_cancel_before_publish_preserves_pointer(pipeline):
    factory, output, _, _ = pipeline
    stop = threading.Event()
    stop.set()
    assert updates.update(factory, force=True, stop=stop, output=output)["state"] == "failed"
    with factory() as s:
        assert all(x.published_revision is None for x in s.scalars(select(IndustryChain)))


def test_current_and_early_disclosure_periods():
    from datetime import date

    assert acquisition.collection_periods(date(2026, 1, 15)) == [
        "2024-12-31",
        "2025-06-30",
        "2025-12-31",
    ]
    assert acquisition.collection_periods(date(2026, 7, 15)) == [
        "2025-06-30",
        "2025-12-31",
        "2026-06-30",
    ]
    assert acquisition.collection_periods(date(2026, 10, 14)) == ["2025-12-31", "2026-06-30"]


def test_provider_degradation_is_rejected_before_snapshot_selection_changes(seeded):
    report = dict(
        universe=4, profile_count=4, business_count=4, financial_count=4, periods=["2025-12-31"]
    )
    acquisition.validate_collection(report, seeded)
    for field in ("profile_count", "business_count", "financial_count"):
        with pytest.raises(ValueError, match="覆盖不足"):
            acquisition.validate_collection({**report, field: 1}, seeded)
    with seeded.begin() as s:
        s.add(BusinessCollection(id="old", state="complete", payload=report))
    with pytest.raises(ValueError, match="覆盖明显下降"):
        acquisition.validate_collection(
            {
                **report,
                "universe": 100,
                "profile_count": 100,
                "business_count": 100,
                "financial_count": 94,
            },
            seeded,
        )


def test_repeated_acquisition_reuses_immutable_snapshots_and_can_revert(
    seeded, monkeypatch, tmp_path
):
    collector = Mock()
    monkeypatch.setattr(acquisition, "BusinessCollector", Mock(return_value=collector))
    codes = [f"{i:06d}.SZ" for i in range(1, 5)]

    def acquire(text, timestamp):
        profiles = [dict(SECUCODE=code, MAIN_BUSINESS=text, ORG_PROFIE="介绍") for code in codes]
        finance = [
            dict(
                SECUCODE=code,
                REPORT_DATE="2025-12-31",
                MAINOP_TYPE="2",
                ITEM_NAME="产品",
                MAIN_BUSINESS_INCOME=10,
            )
            for code in codes
        ]
        envelope = [{"collected_at": timestamp}]
        collector.all.side_effect = [(profiles, envelope), (finance, envelope)]
        return acquisition.collect(seeded, strict=True, refresh=True, cache=tmp_path)

    original = acquire("旧业务", "2026-01-01T00:00:00+00:00")
    repeated = acquire("旧业务", "2026-01-02T00:00:00+00:00")
    assert original["snapshot_hashes"] == repeated["snapshot_hashes"]
    with seeded() as s:
        assert s.scalar(select(func.count()).select_from(BusinessSnapshot)) == 4
    acquire("新业务", "2026-01-03T00:00:00+00:00")
    restored = acquire("旧业务", "2026-01-04T00:00:00+00:00")
    assert restored["snapshot_hashes"] == original["snapshot_hashes"]
    with seeded() as s:
        assert acquisition.snapshots(s)[codes[0]].payload["profile"]["MAIN_BUSINESS"] == "旧业务"
        assert s.scalar(select(func.count()).select_from(BusinessSnapshot)) == 8


def test_no_success_record_is_fabricated_by_failure(seeded):
    with seeded.begin() as s:
        s.add(
            ChainUpdateRun(
                id="failed", state="failed", payload={"error": "失败"}, finished_at=utcnow()
            )
        )
    with seeded() as s:
        result = updates.status(s)
        assert result["last_success_at"] is None and result["error"] == "失败"


def test_maintenance_detects_historical_leaders_and_rechecks_weekly(seeded, monkeypatch):
    doc = sample()
    rid = import_content(seeded, doc)["revision_id"]
    review_content(seeded, rid, "pytest", "测试原有历史证据，不视为最新依据")
    publish_content(seeded, rid)
    tasks, sources = updates.maintenance_inventory(seeded)
    assert tasks and sources
    probe = Mock(return_value=[dict(url=u, state="needs_review") for u in sources])
    monkeypatch.setattr(updates, "probe_evidence", probe)
    first = updates.check_maintenance(seeded)
    assert first["source_review_count"] == len(sources)
    updates.check_maintenance(seeded, first)
    assert probe.call_count == 1
    old = {
        **first,
        "evidence_checked_at": (datetime.now(updates.TZ) - timedelta(days=8)).isoformat(),
    }
    updates.check_maintenance(seeded, old)
    assert probe.call_count == 2


def test_polling_endpoint_is_read_only_and_history_remains_available(pipeline):
    factory, output, _, _ = pipeline
    updates.update(factory, force=True, output=output)
    app = FastAPI()
    app.include_router(router)

    def db():
        with factory() as s:
            yield s

    app.dependency_overrides[database] = db
    with TestClient(app) as c:
        state = c.get("/api/industry-chains/update-status").json()
        assert state["state"] == "published"
        latest = c.get("/api/industry-chains/sw-bank/version").json()
        assert (
            c.get("/api/industry-chains/sw-bank?revision=" + latest["revision_id"]).status_code
            == 200
        )
        assert c.get("/api/industry-chains/unknown/version").status_code == 404
        assert c.post("/api/industry-chains/update-status").status_code == 405
