from datetime import datetime, timezone
from types import SimpleNamespace

from app.api import free_prices
from app.jobs.leaders import refresh_index_leaders
from app.models import Factor, HistoryBar, HistoryImport, Quote, Representative, Stock
from fastapi import BackgroundTasks
from sqlalchemy import select


def test_global_search_has_pinyin_and_is_not_limited_to_representatives(client):
    assert client.get("/api/search?keyword=yyh").json()[0]["name"] == "乙银行"
    assert client.get("/api/search?keyword=yiyinhang").json()[0]["id"] == 2
    assert client.get("/api/search?keyword=000002").json()[0]["id"] == 2
    assert client.get("/api/search?keyword=%20").json() == []
    assert client.get("/api/stocks").json()["total"] == 4


def test_codes_empty_order_and_navigation_are_server_side(client):
    assert client.get("/api/stocks?codes=").json()["total"] == 0
    query = "/api/stocks?codes=000004.SZ,000001.SZ,000002.SZ"
    assert [s["id"] for s in client.get(query).json()["items"]] == [4, 1, 2]
    nav = client.get(query + "&neighbor_of=1&page_size=1&page=3").json()["navigation"]
    assert nav == dict(previous_id=4, next_id=2, position=2, total=3)
    assert client.get(query + "&neighbor_of=3").json()["navigation"]["position"] == 0


def test_numeric_sort_keeps_null_last_in_both_directions(client, seeded):
    with seeded.begin() as s:
        s.get(Quote, (1, "20260105")).turnover_rate = 8
        s.get(Quote, (2, "20260105")).turnover_rate = 2
    for direction, first in [("asc", 2), ("desc", 1)]:
        rows = client.get("/api/stocks?sort=turnover_" + direction).json()["items"]
        assert rows[0]["id"] == first
        assert rows[-1]["turnover_rate"] is None


def test_breadth_counts_only_valid_quotes_and_ignores_list_search(client):
    result = client.get(
        "/api/industry-summary?industry_id=bank&keyword=甲&scope=representatives"
    ).json()
    assert (result["total"], result["up"], result["down"], result["missing"]) == (3, 1, 1, 1)
    assert result["index"] is None


def test_unadjusted_does_not_require_factor_and_suspension_keeps_status(client, seeded):
    with seeded.begin() as s:
        s.delete(s.get(Factor, (1, "20260105")))
    result = client.get("/api/stocks/1/prices?adjustment=none&range=10y").json()
    assert result["points"][0]["close"] == 10
    assert result["adjustment"] == "none"
    suspended = client.get("/api/stocks/3/prices").json()
    assert suspended["points"][0]["status"] == "suspended"
    assert suspended["missing_days"] == []


def test_failed_refresh_serves_old_basis_and_raw_candle(seeded):
    with seeded.begin() as s:
        s.add(
            HistoryBar(
                stock_id=1,
                trade_date="20260105",
                raw_open=9,
                raw_high=11,
                raw_low=8,
                raw_close=10,
                adjusted_open=4.5,
                adjusted_high=5.5,
                adjusted_low=4,
                adjusted_close=5,
                volume=100,
            )
        )
        s.add(
            HistoryImport(
                stock_id=1,
                start_date="20200101",
                basis_date="20260105",
                source="test",
                state="complete",
                error="offline",
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
        )
    with seeded() as s:
        stock = s.get(Stock, 1)
        for adjustment, expected in [("qfq", 5), ("none", 10)]:
            result = free_prices(s, stock, "20200101", "20260106", BackgroundTasks(), adjustment)
            assert result["points"][0]["close"] == expected
            assert result["basis_date"] == "20260105"
            assert result["stale"] and not result["pending"]
            assert "offline" in result["message"]


def test_source_rank_not_renumbered_or_replaced_by_fourth_member(seeded):
    def ak(name, **params):
        if name == "index_realtime_sw":
            return []
        if params["symbol"] == "bank":
            return [
                {"证券代码": code, "最新权重": weight}
                for code, weight in [("000999", 40), ("000002", 30), ("000998", 20), ("000001", 10)]
            ]
        return [{"证券代码": "000004", "最新权重": 100}]

    result = refresh_index_leaders(SimpleNamespace(ak=ak), seeded)
    assert any("未匹配" in w for w in result["warnings"])
    with seeded() as s:
        reps = list(s.scalars(select(Representative).where(Representative.industry_id == "bank")))
        assert len(reps) == 1
        assert reps[0].stock_id == 2 and reps[0].position == 1
        assert "第 2 位" in reps[0].reason


def test_industry_index_uses_same_day_and_previous_session(seeded, monkeypatch):
    from app.jobs import index_quotes
    from app.models import Calendar, Industry, IndustryIndexQuote

    rows = [
        {"代码": "801780", "日期": "2026-01-02", "收盘": 100},
        {"代码": "801780", "日期": "2026-01-05", "收盘": 103},
    ]
    fake = SimpleNamespace(ak=lambda *a, **k: rows, close=lambda: None)
    monkeypatch.setattr(index_quotes, "Session", seeded)
    monkeypatch.setattr(index_quotes, "FreeProvider", lambda: fake)
    with seeded.begin() as s:
        s.add(Industry(id="801780.SI", name="银行指数"))
        s.add(Calendar(exchange="SSE", date="20260102", is_open=True, source="test"))
    index_quotes.warm_index("801780.SI", "20260105")
    with seeded() as s:
        record = s.get(IndustryIndexQuote, ("801780.SI", "20260105"))
        assert record.close == 103
        assert abs(record.pct_chg - 3) < 1e-8
    # A failed refresh preserves an already verified quote.
    rows.pop()
    index_quotes.warm_index("801780.SI", "20260105")
    with seeded() as s:
        assert s.get(IndustryIndexQuote, ("801780.SI", "20260105")).close == 103
    index_quotes.warm_index("801780.SI", "20260106")
    with seeded() as s:
        record = s.get(IndustryIndexQuote, ("801780.SI", "20260106"))
        assert record.close is None and record.error


def test_calendar_failure_preserves_history_and_records_error(seeded, monkeypatch):
    from app.jobs import free_sync
    from app.models import Publication

    with seeded.begin() as s:
        s.get(Publication, "20260105").source = "免费公开数据"
        s.add(
            HistoryImport(
                stock_id=1,
                start_date="20250101",
                basis_date="20260105",
                source="test",
                state="complete",
                missing_days="[]",
            )
        )
        s.add(HistoryBar(stock_id=1, trade_date="20260105", raw_close=10, adjusted_close=10))
    fake = SimpleNamespace(calendar=lambda: [], close=lambda: None)
    monkeypatch.setattr(free_sync, "Session", seeded)
    monkeypatch.setattr(free_sync, "FreeProvider", lambda: fake)
    free_sync.warm_history(1, "20200101")
    with seeded() as s:
        record = s.get(HistoryImport, 1)
        assert record.state == "complete" and record.start_date == "20250101"
        assert "日历" in record.error
        assert s.get(HistoryBar, (1, "20260105")).adjusted_close == 10
