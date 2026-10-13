import json
from types import SimpleNamespace

import httpx
import pytest
from app.api import free_prices
from app.jobs.free_sync import FreeSyncService
from app.models import Calendar, HistoryBar, HistoryImport, Publication, Quote, Stock
from app.providers.free import SOURCE, FreeProvider
from app.providers.tushare import ProviderError
from fastapi import BackgroundTasks
from sqlalchemy import func, select


def provider(tmp_path, handler):
    return FreeProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler)), interval=0, cache_dir=tmp_path
    )


def test_eastmoney_pagination_and_yuan_units(tmp_path):
    def handle(request):
        page = int(request.url.params["pn"])
        return httpx.Response(
            200,
            json={
                "rc": 0,
                "data": {
                    "total": 2,
                    "diff": [
                        {
                            "f12": f"{page:06d}",
                            "f14": "样本",
                            "f2": 10,
                            "f3": -2,
                            "f6": 12345,
                            "f8": 2.69,
                            "f9": 26.41,
                            "f20": 90000,
                            "f21": 25000,
                            "f23": 1.98,
                            "f124": 1791531270,
                        }
                    ],
                },
            },
        )

    p = provider(tmp_path, handle)
    rows = p.eastmoney_snapshot()
    assert len(rows) == 2
    assert rows[0]["amount"] == 12345
    assert rows[0]["market_cap"] == 90000
    assert rows[0]["float_market_cap"] == 25000
    assert (rows[0]["turnover_rate"], rows[0]["pe_ratio"], rows[0]["pb_ratio"]) == (
        2.69,
        26.41,
        1.98,
    )
    assert rows[0]["pe_basis"] == "动态"
    assert rows[0]["date"] == "20261009"


def test_repeated_or_truncated_page_rejected(tmp_path):
    row = {
        "f12": "000001",
        "f14": "样本",
        "f2": 10,
        "f3": 0,
        "f6": 1,
        "f20": 100,
        "f124": 1791531270,
    }
    p = provider(
        tmp_path, lambda _: httpx.Response(200, json={"rc": 0, "data": {"total": 2, "diff": [row]}})
    )
    with pytest.raises(ProviderError, match="重复"):
        p.eastmoney_snapshot()


def test_tencent_units_date_and_bse(tmp_path):
    fields = [""] * 74
    for i, value in {
        1: "安徽凤凰",
        2: "920000",
        3: "14.19",
        30: "20261009153542",
        32: "2.09",
        38: "1.23",
        39: "21.20",
        44: "8.17",
        45: "13.01",
        46: "1.92",
        57: "992.3736",
        72: "57593925",
        73: "91680000",
    }.items():
        fields[i] = value
    p = provider(
        tmp_path, lambda _: httpx.Response(200, text='v_bj920000="' + "~".join(fields) + '";')
    )
    row = p.tencent_snapshot(["920000.BJ"])[0]
    assert row["ts_code"] == "920000.BJ"
    assert row["amount"] == pytest.approx(9923736)
    assert row["market_cap"] == pytest.approx(1301000000)
    assert row["float_market_cap"] == pytest.approx(817000000)
    assert row["turnover_rate"] == 1.23
    assert (row["pe_ratio"], row["pe_basis"], row["pb_ratio"]) == (21.2, "行情源口径", 1.92)
    assert (row["total_shares"], row["float_shares"]) == (91680000, 57593925)
    assert row["date"] == "20261009"


def test_permission_error_not_retried(tmp_path):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(403)

    p = provider(tmp_path, handle)
    with pytest.raises(ProviderError, match="拒绝访问"):
        p.request("https://example.org/", {})
    assert len(calls) == 1


def test_history_sources_parse_real_ohlc_positions(tmp_path):
    eastmoney = provider(tmp_path, lambda _: httpx.Response(200))
    eastmoney.request = lambda *a, **k: {
        "code": "000001",
        "klines": ["2026-01-05,9,10,11,8,1000"],
    }
    assert eastmoney.history("000001", "20260105", "20260105") == [
        {
            "date": "20260105",
            "open": 9,
            "high": 11,
            "low": 8,
            "close": 10,
            "volume": 1000,
        }
    ]
    eastmoney.request = lambda *a, **k: {
        "code": "000001",
        "klines": ["2026-01-05,9,10,7,8,1000"],
    }
    with pytest.raises(ProviderError, match="关系异常"):
        eastmoney.history("000001", "20260105", "20260105")

    tencent = provider(
        tmp_path,
        lambda _: httpx.Response(
            200,
            json={
                "code": 0,
                "data": {"sz000001": {"day": [["2026-01-05", "9", "10", "11", "8", "1000"]]}},
            },
        ),
    )
    assert tencent.tencent_history("000001", "20260105", "20260105") == [
        {
            "date": "20260105",
            "open": 9,
            "high": 11,
            "low": 8,
            "close": 10,
            "volume": 1000,
        }
    ]


def test_history_anchored_across_ranges_and_atomic_failure(seeded):
    with seeded.begin() as s:
        s.add(Calendar(exchange="SZSE", date="20251231", is_open=True, source="fixture"))
        stock = s.get(Stock, 1)

    class Fake:
        def history(self, symbol, start, end, adjusted=False):
            return [
                {
                    "date": "20251231",
                    "open": 17 if adjusted else 8.5,
                    "high": 19 if adjusted else 9.5,
                    "low": 16 if adjusted else 8,
                    "close": 18 if adjusted else 9,
                    "volume": 300,
                },
                {
                    "date": "20260105",
                    "open": 24 if adjusted else 9.5,
                    "high": 26 if adjusted else 10.5,
                    "low": 23 if adjusted else 9,
                    "close": 25 if adjusted else 10,
                    "volume": 500,
                },
            ]

    service = FreeSyncService(Fake(), seeded)
    assert service.history_one(stock, "20250105", "20260105") == "complete"
    assert service.history_one(stock, "20250105", "20260105") == "skipped"
    with seeded() as s:
        h = s.get(HistoryBar, (1, "20251231"))
        assert h.adjusted_close == 7.2
        assert (h.adjusted_open, h.adjusted_high, h.adjusted_low) == (6.8, 7.6, 6.4)
        assert h.volume == 300
        for start in ("20251201", "20250105"):
            result = free_prices(s, stock, start, "20260105", BackgroundTasks())
            assert result["basis_date"] == "20260105"
            assert result["points"][-1]["close"] == 10
            assert result["points"][-1]["open"] == 9.6
    service.provider = SimpleNamespace(history=lambda *a, **k: [{"date": "20251231", "close": 18}])
    with pytest.raises(ProviderError, match="末日缺失"):
        service.history_one(stock, "20250105", "20260105", force=True)
    with seeded() as s:
        assert s.get(HistoryBar, (1, "20251231")).adjusted_close == 7.2
        assert s.get(HistoryImport, 1).error
        assert s.scalar(select(func.count()).select_from(HistoryBar)) == 2


def test_legacy_close_only_history_is_refetched_for_candles(seeded):
    with seeded.begin() as s:
        s.add(HistoryBar(stock_id=1, trade_date="20260105", raw_close=10, adjusted_close=10))
        s.add(
            HistoryImport(
                stock_id=1,
                start_date="20250105",
                basis_date="20260105",
                source="旧版收盘价缓存",
                state="complete",
                missing_days="[]",
                error=None,
            )
        )
        stock = s.get(Stock, 1)
    with seeded() as s:
        result = free_prices(s, stock, "20250105", "20260105", BackgroundTasks())
        assert result["pending"] and result["points"] == []

    class Fake:
        def history(self, symbol, start, end, adjusted=False):
            return [
                {"date": "20260105", "open": 9, "high": 11, "low": 8, "close": 10, "volume": 500}
            ]

    assert FreeSyncService(Fake(), seeded).history_one(stock, "20250105", "20260105") == "complete"
    with seeded() as s:
        bar = s.get(HistoryBar, (1, "20260105"))
        assert (bar.adjusted_open, bar.adjusted_high, bar.adjusted_low, bar.volume) == (
            9,
            11,
            8,
            500,
        )


def test_legacy_candle_without_volume_is_refetched(seeded):
    with seeded.begin() as s:
        s.add(
            HistoryBar(
                stock_id=1,
                trade_date="20260105",
                raw_close=10,
                adjusted_open=9,
                adjusted_high=11,
                adjusted_low=8,
                adjusted_close=10,
            )
        )
        s.add(
            HistoryImport(
                stock_id=1,
                start_date="20250105",
                basis_date="20260105",
                source="旧版 K 线缓存",
                state="complete",
                missing_days="[]",
                error=None,
            )
        )
        stock = s.get(Stock, 1)
    with seeded() as s:
        assert free_prices(s, stock, "20250105", "20260105", BackgroundTasks())["pending"]

    class Fake:
        def history(self, symbol, start, end, adjusted=False):
            return [
                {"date": "20260105", "open": 9, "high": 11, "low": 8, "close": 10, "volume": 230}
            ]

    assert FreeSyncService(Fake(), seeded).history_one(stock, "20250105", "20260105") == "complete"
    with seeded() as s:
        assert s.get(HistoryBar, (1, "20260105")).volume == 230


def test_snapshot_failure_preserves_published_day(seeded):
    with seeded.begin() as s:
        s.add(Calendar(exchange="SSE", date="20260105", is_open=True, source="fixture"))
    fake = SimpleNamespace(snapshot=lambda: [], snapshot_source=SOURCE)
    service = FreeSyncService(fake, seeded)
    with pytest.raises(ProviderError, match="不足"):
        service.snapshot("20260105", force=True)
    with seeded() as s:
        assert s.get(Publication, "20260105").source == "Tushare Pro"
        assert s.get(Quote, (1, "20260105")).close == 10


def test_free_snapshot_missing_cap_and_repeat_are_explicit(seeded):
    with seeded.begin() as s:
        s.add(Calendar(exchange="SSE", date="20260105", is_open=True, source="fixture"))
    rows = [
        dict(
            ts_code=f"{i:06d}.SZ",
            date="20260105",
            time="150001",
            close=10,
            pct_chg=-2,
            amount=12345,
            market_cap=None if i == 1 else 1000,
        )
        for i in range(1, 5)
    ]
    fake = SimpleNamespace(snapshot=lambda: rows, snapshot_source=SOURCE)
    service = FreeSyncService(fake, seeded)
    service.snapshot("20260105", force=True)
    service.snapshot("20260105", force=True)
    with seeded() as s:
        p = s.get(Publication, "20260105")
        assert p.missing_cap_count == 1
        assert p.missing_count == 0
        assert s.scalar(select(func.count()).select_from(Quote)) == 4
        assert s.get(Quote, (1, "20260105")).amount == 12345


def test_history_gap_is_not_suspension(seeded):
    with seeded.begin() as s:
        s.add(Calendar(exchange="SZSE", date="20251231", is_open=True, source="fixture"))
        stock = s.get(Stock, 1)
    fake = SimpleNamespace(
        history=lambda *a, **k: [
            {
                "date": "20260105",
                "open": 9.5,
                "high": 11,
                "low": 9,
                "close": 10,
                "volume": 400,
            }
        ]
    )
    service = FreeSyncService(fake, seeded)
    assert service.history_one(stock, "20250105", "20260105") == "partial"
    with seeded() as s:
        assert json.loads(s.get(HistoryImport, 1).missing_days) == ["20251231"]
        result = free_prices(s, stock, "20251201", "20260105", BackgroundTasks())
        assert result["points"][0]["close"] is None
        assert result["complete"] is False


def test_optional_profile_cache_updates_and_throttles(seeded, tmp_path, monkeypatch):
    from app import settings
    from app.jobs import free_sync

    calls = []

    class Fake:
        def profile(self, symbol):
            calls.append(symbol)
            return {"fullname": "完整公司名", "introduction": "介绍", "main_business": "主营"}

        def close(self):
            pass

    monkeypatch.setattr(free_sync, "Session", seeded)
    monkeypatch.setattr(free_sync, "FreeProvider", Fake)
    monkeypatch.setattr(settings, "db_path", lambda: tmp_path / "test.sqlite3")
    free_sync.warm_profile(1)
    free_sync.warm_profile(1)
    with seeded() as s:
        assert s.get(Stock, 1).main_business == "主营"
    assert len(calls) == 1


def test_tencent_long_history_pages_backwards_and_deduplicates(tmp_path):
    from datetime import datetime, timedelta

    p = provider(tmp_path, lambda _: httpx.Response(200))
    days = [(datetime(2020, 1, 1) + timedelta(days=i)).strftime("%Y%m%d") for i in range(1200)]
    cursors = []

    def page(symbol, start, end, adjusted, cursor):
        cursors.append(cursor)
        available = [d for d in days if not cursor or d <= cursor.replace("-", "")]
        return [{"date": d} for d in available[-640:]]

    p._tencent_history_page = page
    result = p.tencent_history("000001", days[0], days[-1])
    assert len(result) == 1200
    assert [r["date"] for r in result] == days
    assert len(cursors) == 2 and cursors[0] == "" and cursors[1]


def test_eastmoney_long_history_is_split_at_calendar_year(tmp_path):
    p = provider(tmp_path, lambda _: httpx.Response(200))
    calls = []

    def year(symbol, start, end, adjusted):
        calls.append((start, end, adjusted))
        return []

    p._history_year = year
    assert p.history("000001", "20241202", "20260105", adjusted=True) == []
    assert calls == [
        ("20241202", "20241231", True),
        ("20250101", "20251231", True),
        ("20260101", "20260105", True),
    ]


def test_long_backfill_extends_calendar_and_short_refresh_preserves_older_bars(seeded):
    with seeded.begin() as s:
        s.get(Publication, "20260105").source = "免费公开数据"
    rows = [
        dict(date=day, open=9, high=11, low=8, close=10, volume=100)
        for day in ["20200102", "20260105"]
    ]
    fake = SimpleNamespace(calendar=lambda: ["20200102", "20260105"], history=lambda *a, **k: rows)
    service = FreeSyncService(fake, seeded)
    result = service.run("20200101", "20260105", command="backfill", codes=["000001.SZ"])
    assert result["failures"] == [] and result["complete"] == 1
    with seeded() as s:
        stock = s.get(Stock, 1)
        assert s.get(Calendar, ("SZSE", "20200102")).is_open
    service.history_one(stock, "20250101", "20260105", force=True)
    with seeded() as s:
        assert s.get(HistoryImport, 1).start_date == "20200101"
        assert s.get(HistoryBar, (1, "20200102")).raw_close == 10
