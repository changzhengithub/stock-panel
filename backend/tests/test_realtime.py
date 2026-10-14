from datetime import datetime
from types import SimpleNamespace

import pytest
from app.models import Publication, Quote, Stock
from app.providers.free import TZ
from app.providers.tushare import ProviderError
from app.realtime import (
    cache_path,
    cache_stale,
    current_bar,
    read_cache,
    refresh,
    snapshot_for,
    validate_snapshot,
    write_cache,
)
from sqlalchemy import select

DAY = "20260106"
NOW = datetime(2026, 1, 6, 11, 0, tzinfo=TZ)


def rows():
    return [
        dict(
            ts_code=f"{i:06d}.SZ",
            name=f"股票{i}",
            date=DAY,
            time="105959",
            pre_close=10,
            open=10,
            high=15,
            low=9,
            close=10 + i,
            pct_chg=(-5, 20, 0, 8)[i - 1],
            volume=1234,
            amount=1000 * i,
            market_cap=10000 * i,
            float_market_cap=5000 * i,
            turnover_rate=i,
            pe_ratio=20,
            pb_ratio=2,
            total_shares=100000,
            float_shares=50000,
            pe_basis="行情源口径",
        )
        for i in range(1, 5)
    ]


def publish(seeded, data=None):
    with seeded() as s:
        stocks = list(s.scalars(select(Stock)))
        value = validate_snapshot(data or rows(), stocks, DAY, NOW)
        value["source"] = "免费公开行情 · 腾讯"
        write_cache(cache_path(s), value)
    return value


def test_live_list_global_sort_pagination_detail_summary_and_history(client, seeded):
    publish(seeded)
    response = client.get("/api/stocks?sort=pct_desc&page_size=1&page=2").json()
    assert response["trade_date"] == DAY
    assert response["total"] == 4
    assert response["items"][0]["id"] == 4
    assert response["items"][0]["quote_time"] == "105959"
    assert response["items"][0]["quote_mode"] == "live"
    detail = client.get("/api/stocks/2").json()
    assert (detail["close"], detail["open"], detail["volume"], detail["pre_close"]) == (
        12,
        10,
        1234,
        10,
    )
    summary = client.get("/api/industry-summary").json()
    assert (summary["trade_date"], summary["up"], summary["down"], summary["flat"]) == (
        DAY,
        2,
        1,
        1,
    )
    status = client.get("/api/data-status").json()
    assert status["trade_date"] == DAY and status["daily_trade_date"] == "20260105"
    assert status["quote_coverage"]["SZSE"] == {"valid": 4, "total": 4}
    chart = client.get("/api/stocks/1/prices?adjustment=none").json()
    assert chart["points"][-1]["date"] == DAY
    assert chart["points"][-1]["close"] == 11
    nav = client.get("/api/stocks?sort=pct_desc&neighbor_of=4").json()["navigation"]
    assert (nav["previous_id"], nav["next_id"]) == (2, 3)
    with seeded() as s:
        assert s.get(Quote, (1, "20260105")).close == 10
        assert s.get(Publication, DAY) is None


def test_same_day_replaces_prices_and_not_daily_bars(client, seeded):
    data = rows()
    for row in data:
        row["date"] = "20260105"
    with seeded() as s:
        value = validate_snapshot(data, list(s.scalars(select(Stock))), "20260105", NOW)
        value["source"] = "免费公开行情 · 腾讯"
        write_cache(cache_path(s), value)
    assert client.get("/api/stocks/1").json()["close"] == 11
    assert client.get("/api/stocks/1/prices?adjustment=none").json()["points"][-1]["close"] == 11
    with seeded() as s:
        assert s.get(Quote, (1, "20260105")).close == 10


def test_market_coverage_is_validated_independently():
    stocks = [SimpleNamespace(ts_code=f"{i:06d}.SZ", exchange="SZSE") for i in range(1, 5)]
    stocks.append(SimpleNamespace(ts_code="920000.BJ", exchange="BSE"))
    with pytest.raises(ProviderError, match="BSE"):
        validate_snapshot(rows(), stocks, DAY, NOW)


def test_old_duplicate_future_data_rejected(seeded):
    with seeded() as s:
        stocks = list(s.scalars(select(Stock)))
    with pytest.raises(ProviderError, match="重复"):
        validate_snapshot(rows() + [rows()[0]], stocks, DAY, NOW)
    for day, clock in [("20260105", "105959"), (DAY, "120000")]:
        data = rows()
        for row in data:
            row.update(date=day, time=clock)
        with pytest.raises(ProviderError, match="尚未返回"):
            validate_snapshot(data, stocks, DAY, NOW)


def test_failed_sources_preserve_cache_and_report_stale(seeded, client):
    value = publish(seeded)

    def fail(*_):
        raise ProviderError("源暂不可用")

    fake = SimpleNamespace(tencent_snapshot=fail, eastmoney_snapshot=fail, close=lambda: None)
    with pytest.raises(ProviderError):
        refresh(seeded, lambda: fake, NOW)
    with seeded() as s:
        cached = read_cache(s)
        assert cached["quotes"] == value["quotes"]
        assert "源暂不可用" in cached["error"]
    status = client.get("/api/data-status").json()
    assert status["stale"] and status["quote_error"]
    assert client.get("/api/stocks/1").json()["quote_stale"]


def test_fallback_to_second_free_source(seeded):
    def fail(*_):
        raise ProviderError("第一源连接失败")

    fake = SimpleNamespace(tencent_snapshot=fail, eastmoney_snapshot=rows, close=lambda: None)
    value = refresh(seeded, lambda: fake, NOW)
    assert value["source"] == "免费公开行情 · 东方财富"
    assert len(value["quotes"]) == 4


def test_missing_today_quote_not_backfilled_from_yesterday(client, seeded):
    value = publish(seeded)
    del value["quotes"]["000001.SZ"]
    with seeded() as s:
        write_cache(cache_path(s), value)
    detail = client.get("/api/stocks/1").json()
    assert detail["close"] is None and detail["quote_date"] is None
    assert detail["status"] == "unavailable"
    assert client.get("/api/stocks?sort=pct_desc").json()["total"] == 3
    summary = client.get("/api/industry-summary").json()
    assert summary["missing"] == 1


def test_new_st_flag_applies_to_search_list_detail_and_counts(client, seeded):
    data = rows()
    data[0]["name"] = "*ST测试"
    publish(seeded, data)
    assert client.get("/api/stocks").json()["total"] == 3
    assert client.get("/api/search?keyword=000001").json() == []
    assert client.get("/api/stocks/1").status_code == 404
    assert client.get("/api/stocks/1/prices").status_code == 404
    assert client.get("/api/data-status").json()["stock_count"] == 3
    assert sum(i["stock_count"] for i in client.get("/api/industries").json()) == 3


def test_snapshot_pinned_per_request_and_older_cache_not_used(seeded):
    publish(seeded)
    with seeded() as s:
        snapshot = snapshot_for(s)
        changed = dict(snapshot, source="changed")
        write_cache(cache_path(s), changed)
        assert snapshot_for(s)["source"] != "changed"
    with seeded.begin() as s:
        s.add(Publication(trade_date="20260107", stock_count=4))
    with seeded() as s:
        assert snapshot_for(s) is None


def test_adjustment_mismatch_never_spliced(seeded):
    data = rows()
    data[0]["pre_close"] = 8
    publish(seeded, data)
    result = dict(points=[dict(date="20260105", close=10)], adjustment="qfq", message=None)
    with seeded() as s:
        current_bar(result, s, s.get(Stock, 1))
    assert len(result["points"]) == 1 and "复权基准" in result["message"]


def test_calendar_rollover_and_closed_market_staleness(seeded):
    value = publish(seeded)
    value.update(expected_date="20260107")
    assert cache_stale(value, datetime(2026, 1, 7, 10, 0, tzinfo=TZ))
    value.update(expected_date=DAY)
    assert not cache_stale(value, datetime(2026, 1, 6, 18, 0, tzinfo=TZ))
    assert not cache_stale(value, datetime(2026, 1, 6, 11, 30, tzinfo=TZ))


def test_current_cache_cannot_regress_to_an_older_day(seeded):
    value = publish(seeded)
    old_rows = rows()
    for row in old_rows:
        row["date"] = "20260105"
    fake = SimpleNamespace(
        tencent_snapshot=lambda _: old_rows, eastmoney_snapshot=lambda: old_rows, close=lambda: None
    )
    with pytest.raises(ProviderError):
        refresh(seeded, lambda: fake, NOW)
    with seeded() as s:
        cached = read_cache(s)
        assert cached["trade_date"] == value["trade_date"]
        assert cached["quotes"] == value["quotes"]
