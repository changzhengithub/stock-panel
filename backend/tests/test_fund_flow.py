"""Source contracts, publication failures, query boundaries and isolated fund APIs."""

from datetime import datetime

import httpx
import pytest
from app.api import database
from app.fund_api import router
from app.fund_flow import board_id, collect, publish, read, scope
from app.models import CodeAlias, FundCache, FundDaily, FundRun, Stock
from app.providers.fund_flow import SOURCE, TZ, FundFlowProvider, normalize
from app.providers.tushare import ProviderError
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("FUND_FLOW_ENABLED", "0")


def row(code="BK1000", net=100, **patch):
    return dict(
        code=code,
        name="测试板块",
        net_amount=net,
        net_rate=2,
        pct_change=1,
        extra_large=40,
        large=60,
        medium=-20,
        small=-80,
        lead_stock=None,
        lead_code=None,
        trade_date="20260105",
        source_as_of="2026-01-05T15:30:00+08:00",
        **patch,
    )


def batch(rows, period="today"):
    return dict(
        rows=rows,
        total=len(rows),
        source=SOURCE,
        trade_date="20260105",
        source_as_of="2026-01-05T15:30:00+08:00",
        period=period,
    )


@pytest.fixture
def fund_client(seeded):
    app = FastAPI()
    app.include_router(router)

    def db():
        with seeded() as s:
            yield s

    app.dependency_overrides[database] = db
    with TestClient(app) as c:
        yield c


def raw(code="BK1000", **patch):
    return {
        "f12": code,
        "f14": "板块",
        "f124": datetime(2026, 1, 5, 15, 30, tzinfo=TZ).timestamp(),
        "f62": 100,
        "f184": 2.5,
        "f3": 1.5,
        "f66": 40,
        "f72": 60,
        **patch,
    }


@pytest.mark.parametrize(
    "period,fields",
    [
        ("today", ("f62", "f184", "f3")),
        ("5d", ("f164", "f165", "f109")),
        ("10d", ("f174", "f175", "f160")),
    ],
)
def test_period_mapping_does_not_substitute_today(period, fields):
    r = normalize(raw(**dict(zip(fields, (-120000000, -3.5, 8)))), period)
    assert (r["net_amount"], r["net_rate"], r["pct_change"]) == (-120000000, -3.5, 8)
    assert r["trade_date"] == "20260105"


@pytest.mark.parametrize("value", ["-", None, "NaN", "inf"])
def test_missing_values_do_not_become_zero(value):
    assert normalize(raw(f62=value), "today")["net_amount"] is None


def test_source_code_and_same_date_full_pagination():
    def transport(request):
        page = int(request.url.params["pn"])
        return httpx.Response(200, json={"data": {"total": 2, "diff": [raw(f"BK100{page}")]}})

    p = FundFlowProvider(httpx.MockTransport(transport))
    try:
        data = p.listing("concept", "today")
        assert [r["code"] for r in data["rows"]] == ["BK1001", "BK1002"]
    finally:
        p.close()


@pytest.mark.parametrize(
    "mode", ["duplicate", "changed_total", "empty", "date_mismatch", "no_time"]
)
def test_bad_source_batch_is_rejected(mode):
    def transport(request):
        page = int(request.url.params["pn"])
        second = (
            raw(
                "BK1002",
                f124=None if mode == "no_time" else datetime(2026, 1, 2, 15, tzinfo=TZ).timestamp(),
            )
            if mode in ("date_mismatch", "no_time")
            else raw("BK1000" if mode == "duplicate" else "BK1002")
        )
        return httpx.Response(
            200,
            json={
                "data": {
                    "total": 3 if mode == "changed_total" and page > 1 else 2,
                    "diff": [raw()] if page == 1 else [] if mode == "empty" else [second],
                }
            },
        )

    p = FundFlowProvider(httpx.MockTransport(transport))
    try:
        with pytest.raises(ProviderError):
            p.listing("industry", "today")
    finally:
        p.close()


def test_transport_error_does_not_expose_proxy_secret():
    def transport(request):
        raise httpx.ConnectError("http://user:secret@proxy.invalid", request=request)

    p = FundFlowProvider(httpx.MockTransport(transport))
    try:
        with pytest.raises(ProviderError) as e:
            p.listing("industry", "today")
        assert "secret" not in str(e.value)
    finally:
        p.close()


def test_history_identity_and_provisional_flags():
    def transport(request):
        return httpx.Response(
            200,
            json={
                "data": {
                    "code": "BK1000",
                    "klines": ["2026-01-05,100,-80,-20,60,40,2,-1,-1,1,1,0,0,0,0"],
                }
            },
        )

    p = FundFlowProvider(httpx.MockTransport(transport))
    try:
        h = p.history("BK1000")
        assert h["rows"][0]["net_amount"] == 100
        assert not h["rows"][0]["provisional"]
        with pytest.raises(ProviderError):
            p.history("BK1001")
    finally:
        p.close()


def test_idempotent_publication_and_same_name_different_types(seeded):
    data = batch([row()])
    key = scope("concept", "today")
    v1 = publish(seeded, key, "concept", data)
    assert publish(seeded, key, "concept", data) == v1
    publish(seeded, scope("industry", "today"), "industry", data)
    with seeded() as s:
        assert s.scalar(select(func.count()).select_from(FundCache)) == 2
        assert read(s, key)["rows"][0]["net_amount"] == 100
    assert board_id("industry", "BK1000") != board_id("concept", "BK1000")


def test_failed_collect_retains_previous_batch_and_backoff(seeded):
    key = scope("concept", "today")
    version = publish(seeded, key, "concept", batch([row()]))

    class Broken:
        def listing(self, *args):
            raise ProviderError("source unavailable")

        def close(self):
            pass

    r = collect("concept", "today", sessions=seeded, provider_factory=Broken, force=True)
    assert r["error"] == "source unavailable"
    with seeded() as s:
        assert read(s, key)["batch_id"] == version
        assert s.get(FundRun, key).retry_at
    assert (
        collect("concept", "today", sessions=seeded, provider_factory=Broken)["skipped"]
        == "backoff"
    )


def test_shrinking_batch_does_not_delete_boards_or_cache(seeded):
    key = scope("concept", "today")
    publish(seeded, key, "concept", batch([row(f"BK{i}") for i in range(1000, 1010)]))
    with pytest.raises(ProviderError):
        publish(seeded, key, "concept", batch([row()]))
    with seeded() as s:
        assert len(read(s, key)["rows"]) == 10


def test_history_retains_older_days_and_excludes_provisional_daily_store(seeded):
    publish(seeded, scope("concept", "today"), "concept", batch([row()]))
    key = scope("concept", "daily", "BK1000", "history")

    def daily(day, provisional=False):
        return dict(trade_date=day, net_amount=100, net_rate=2, provisional=provisional)

    publish(
        seeded,
        key,
        "concept",
        batch([daily("20260102"), daily("20260105"), daily("20260106", True)], "daily"),
        "BK1000",
        "history",
    )
    publish(
        seeded,
        key,
        "concept",
        batch([daily("20260105"), daily("20260106", True)], "daily"),
        "BK1000",
        "history",
    )
    with seeded() as s:
        assert len(read(s, key)["rows"]) == 3
        assert s.scalar(select(func.count()).select_from(FundDaily)) == 2


def test_full_sort_pagination_and_search_independent_overview(seeded, fund_client):
    rows = [row(f"BK{1000 + i}", net=i - 15 if i != 29 else None) for i in range(30)]
    publish(seeded, scope("concept", "today"), "concept", batch(rows))
    r = fund_client.get("/api/hot-sectors").json()
    assert r["items"][0]["code"] == "BK1028" and r["total"] == 30
    second = fund_client.get("/api/hot-sectors?page=2").json()
    assert second["items"][-1]["net_amount"] is None
    search = fund_client.get("/api/hot-sectors?keyword=BK1000").json()
    assert search["total"] == 1 and search["overview"] == r["overview"]
    for direction in ("in", "out"):
        items = fund_client.get("/api/hot-sectors", params={"direction": direction}).json()["items"]
        assert all(x["net_amount"] > 0 if direction == "in" else x["net_amount"] < 0 for x in items)


def test_empty_states_unknown_id_and_query_validation(fund_client):
    r = fund_client.get("/api/hot-sectors").json()
    assert not r["items"] and r["meta"]["quality_status"] == "unavailable"
    assert fund_client.get("/api/hot-sectors/EM-concept-BK9999").status_code == 404
    assert fund_client.get("/api/hot-sectors?period=week").status_code == 422
    assert fund_client.get("/api/hot-sectors?page_size=2").status_code == 422


def test_shared_universe_aliases_suspended_and_unmatched(seeded, fund_client):
    publish(seeded, scope("concept", "today"), "concept", batch([row()]))
    with seeded.begin() as s:
        s.get(Stock, 2).name = "*ST测试"
        s.add(CodeAlias(code="000099.SZ", stock_id=1))
    members = [row(f"{i:06d}", 100, ts_code=f"{i:06d}.SZ") for i in (1, 2, 3, 99, 999)]
    publish(
        seeded,
        scope("concept", "today", "BK1000", "stocks"),
        "concept",
        batch(members),
        "BK1000",
        "stocks",
    )
    r = fund_client.get("/api/hot-sectors/EM-concept-BK1000/stocks").json()
    assert r["source_count"] == 5 and r["total"] == 3
    assert r["filtered_count"] == 1 and r["unmatched_count"] == 1
    assert 3 in [x["stock_id"] for x in r["items"]]


def test_failure_and_stale_date_metadata_keeps_numeric_values(seeded, fund_client):
    key = scope("concept", "today")
    publish(seeded, key, "concept", batch([row()]))
    with seeded.begin() as s:
        s.add(
            FundRun(
                key=key,
                started_at="2026-01-05T00:00:00+00:00",
                finished_at="2026-01-05T00:01:00+00:00",
                error="源失败",
                retry_at=None,
            )
        )
    r = fund_client.get("/api/hot-sectors").json()
    assert r["meta"]["stale"] and r["meta"]["trade_date"] == "20260105"
    assert r["items"][0]["net_amount"] == 100


@pytest.mark.parametrize("size", [20, 50, 100])
def test_valid_query_integer_sizes_are_parsed(fund_client, size):
    assert fund_client.get("/api/hot-sectors", params={"page_size": size}).status_code == 200


def test_history_accepts_explicit_window_and_inserts_calendar_gap(seeded, fund_client):
    from app.models import Calendar

    publish(seeded, scope("concept", "today"), "concept", batch([row()]))
    with seeded.begin() as s:
        s.add(Calendar(exchange="SSE", date="20260103", is_open=True, source="fixture"))
    days = [
        dict(trade_date=d, net_amount=100, net_rate=2, provisional=False)
        for d in ("20260102", "20260105")
    ]
    publish(
        seeded,
        scope("concept", "daily", "BK1000", "history"),
        "concept",
        batch(days, "daily"),
        "BK1000",
        "history",
    )
    r = fund_client.get("/api/hot-sectors/EM-concept-BK1000/history?days=60")
    assert r.status_code == 200
    gap = r.json()["items"][1]
    assert gap["trade_date"] == "20260103" and gap["gap"] and gap["net_amount"] is None


def test_scope_process_lock_prevents_duplicate_collector(seeded):
    import fcntl
    import hashlib
    from pathlib import Path

    key = scope("concept", "today")
    with seeded() as s:
        path = Path(s.get_bind().url.database)
    lock = path.with_name(
        path.name + ".fund-" + hashlib.sha256(key.encode()).hexdigest()[:16] + ".lock"
    )
    with lock.open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = collect("concept", "today", sessions=seeded, force=True)
        assert result["skipped"] == "running"
        with seeded() as s:
            assert s.get(FundRun, key) is None
        fcntl.flock(stream, fcntl.LOCK_UN)


def test_backup_command_does_not_migrate_before_copy(seeded, tmp_path, monkeypatch):
    import sqlite3
    import sys

    from app import cli

    with seeded() as s:
        db_path = s.get_bind().url.database
    backup = tmp_path / "before-migration.sqlite3"
    monkeypatch.setenv("STOCK_DB_PATH", db_path)
    monkeypatch.setattr(sys, "argv", ["stock-panel", "backup", "--output", str(backup)])

    def unexpected_migration():
        raise AssertionError("backup must run before migrations")

    monkeypatch.setattr(cli, "migrate", unexpected_migration)
    assert cli.main() == 0
    with sqlite3.connect(backup) as c:
        assert c.execute("select count(*) from stocks").fetchone()[0] == 4


def test_flow_chart_uses_complete_batch_both_signs_and_excludes_zero_missing(seeded, fund_client):
    rows = [row(f"BK{1000 + i}", net=i - 15 if i != 29 else None) for i in range(30)]
    publish(seeded, scope("concept", "today"), "concept", batch(rows))
    full = fund_client.get("/api/hot-sectors").json()
    filtered = fund_client.get(
        "/api/hot-sectors?keyword=BK1000&direction=out&sort=net_asc&page=2"
    ).json()
    assert full["chart"] == filtered["chart"]
    assert len(full["chart"]["inflows"]) == 10 and len(full["chart"]["outflows"]) == 10
    assert all(r["net_amount"] > 0 for r in full["chart"]["inflows"])
    assert all(r["net_amount"] < 0 for r in full["chart"]["outflows"])
    assert full["chart"]["inflows"][0]["code"] == "BK1028"
    assert full["chart"]["outflows"][0]["code"] == "BK1000"
