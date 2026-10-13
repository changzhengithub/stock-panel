import pytest
from app.jobs.sync import SyncService
from app.models import Calendar, CodeAlias, Publication, Quote
from app.providers.tushare import PermissionDenied, ProviderError
from sqlalchemy import func, select


class Provider:
    def __init__(self, missing=False):
        self.missing = missing
        self.calls = []

    def all(self, api, **params):
        self.calls.append(api)
        date = params["trade_date"]
        if api == "stock_st":
            raise PermissionDenied("无权限")
        if api == "suspend_d":
            return [
                {
                    "ts_code": "000003.SZ",
                    "trade_date": date,
                    "suspend_type": "S",
                    "suspend_timing": None,
                },
                {
                    "ts_code": "000001.SZ",
                    "trade_date": date,
                    "suspend_type": "S",
                    "suspend_timing": "09:30-10:00",
                },
            ]
        ids = [1, 2, 4] if not self.missing else [1, 4]
        if api == "daily":
            return [
                {
                    "ts_code": f"{i:06d}.SZ",
                    "trade_date": date,
                    "open": 9,
                    "high": 11,
                    "low": 8,
                    "close": 10,
                    "pct_chg": 2,
                    "vol": 123,
                    "amount": 5,
                }
                for i in ids
            ]
        if api == "daily_basic":
            return [{
                "ts_code": f"{i:06d}.SZ", "trade_date": date,
                "total_mv": 20, "circ_mv": 12, "turnover_rate": 2.5,
                "pe_ttm": 18.6, "pb": 1.3, "total_share": 2,
                "float_share": 1.2,
            } for i in ids]
        if api == "adj_factor":
            return [{"ts_code": f"{i:06d}.SZ", "trade_date": date, "adj_factor": 2} for i in ids]
        raise AssertionError(api)


def setup_day(sessions, date):
    with sessions.begin() as s:
        s.add(Calendar(exchange="SZSE", date=date, is_open=True, source="test"))


def test_atomic_publish_units_and_idempotence(seeded):
    setup_day(seeded, "20260106")
    provider = Provider()
    service = SyncService(provider, seeded)
    assert service.sync_day("20260106") == "published"
    assert service.sync_day("20260106") == "skipped"
    service.sync_day("20260106", force=True)
    with seeded() as s:
        q = s.get(Quote, (1, "20260106"))
        assert q.amount == 5000 and q.market_cap == 200000 and q.status == "trading"
        assert (q.open, q.high, q.low, q.close) == (9, 11, 8, 10)
        assert q.volume == 123
        assert (q.float_market_cap, q.turnover_rate) == (120000, 2.5)
        assert (q.pe_ratio, q.pe_basis, q.pb_ratio) == (18.6, "TTM", 1.3)
        assert (q.total_shares, q.float_shares) == (20000, 12000)
        assert s.get(Quote, (3, "20260106")).status == "suspended"
        assert q.is_st is None
        assert (
            s.scalar(select(func.count()).select_from(Quote).where(Quote.trade_date == "20260106"))
            == 4
        )


def test_failed_day_preserves_previous_snapshot(seeded):
    setup_day(seeded, "20260106")
    with pytest.raises(ProviderError, match="缺失"):
        SyncService(Provider(missing=True), seeded).sync_day("20260106")
    with seeded() as s:
        assert s.get(Publication, "20260106") is None
        assert s.scalar(select(func.max(Publication.trade_date))) == "20260105"
        assert s.get(Quote, (1, "20260106")) is None


def test_failed_forced_refresh_does_not_remove_published_day(seeded):
    with pytest.raises(ProviderError):
        SyncService(Provider(missing=True), seeded).sync_day("20260105", force=True)
    with seeded() as s:
        assert s.get(Publication, "20260105") is not None
        assert s.get(Quote, (1, "20260105")).pct_chg == 2.5


def test_code_alias_joins_same_identity(seeded):
    with seeded.begin() as s:
        s.add(CodeAlias(code="920001.BJ", stock_id=1))

    class Renamed(Provider):
        def all(self, api, **params):
            rows = super().all(api, **params)
            for row in rows:
                if row["ts_code"] == "000001.SZ":
                    row["ts_code"] = "920001.BJ"
            return rows

    setup_day(seeded, "20260106")
    SyncService(Renamed(), seeded).sync_day("20260106")
    with seeded() as s:
        assert s.get(Quote, (1, "20260106")).close == 10


def test_permission_failure_is_not_ignored(seeded):
    class Denied(Provider):
        def all(self, *args, **kwargs):
            raise PermissionDenied("daily 无权限")

    setup_day(seeded, "20260106")
    with pytest.raises(PermissionDenied):
        SyncService(Denied(), seeded).sync_day("20260106")
