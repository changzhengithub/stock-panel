from datetime import datetime, timedelta

import pytest
from app.jobs.sync import SyncService
from app.models import Calendar, CodeAlias, Stock
from app.providers.tushare import ProviderError
from sqlalchemy import select


class MetadataProvider:
    rename = False
    missing_exchange = False

    def all(self, api, **params):
        if api == "stock_basic":
            exchange = params["exchange"]
            if self.missing_exchange and exchange == "BSE":
                return []
            code = {
                "SSE": "600001.SH",
                "SZSE": "000001.SZ",
                "BSE": "920001.BJ" if self.rename else "830001.BJ",
            }[exchange]
            return [
                dict(
                    ts_code=code,
                    symbol=code.split(".")[0],
                    name="样本",
                    exchange=exchange,
                    market="主板" if exchange != "BSE" else "北交所",
                    list_date="20200101",
                )
            ]
        if api == "bse_mapping":
            return [{"o_code": "830001.BJ", "n_code": "920001.BJ"}]
        if api == "index_classify":
            return [{"index_code": "bank_l2" if params["level"] == "L2" else "bank", "industry_name": "银行"}]
        if api == "index_member_all":
            return [{"ts_code": c, "l2_code": "bank_l2"} for c in ["600001.SH", "000001.SZ", "920001.BJ"]]
        if api == "stock_company":
            return []
        if api == "trade_cal":
            start = datetime.strptime(params["start_date"], "%Y%m%d")
            end = datetime.strptime(params["end_date"], "%Y%m%d")
            return [
                {"cal_date": (start + timedelta(days=i)).strftime("%Y%m%d"), "is_open": 1}
                for i in range((end - start).days + 1)
            ]
        raise AssertionError(api)


def test_metadata_maps_bse_codes_without_duplicate_stock(sessions, monkeypatch):
    monkeypatch.setattr("app.jobs.sync.level2_categories", lambda: ({"110100": {"code": "110100", "id": "bank_l2", "name": "银行细分", "parent_id": "bank"}}, {"bank_l2": {"code": "110100", "id": "bank_l2", "name": "银行细分", "parent_id": "bank"}}))
    provider = MetadataProvider()
    service = SyncService(provider, sessions)
    service.metadata("20260105", "20260106")
    with sessions() as s:
        identity = s.get(CodeAlias, "830001.BJ").stock_id
        assert s.get(CodeAlias, "920001.BJ").stock_id == identity
        assert s.get(Calendar, ("BSE", "20260105")).source.endswith("参考上交所日历")
    provider.rename = True
    service.metadata("20260105", "20260106")
    with sessions() as s:
        assert len(list(s.scalars(select(Stock)))) == 3
        assert s.get(Stock, identity).ts_code == "920001.BJ"
        assert s.get(Stock, identity).industry_id == "bank"
        assert s.get(Stock, identity).industry_l2_id == "bank_l2"


def test_incomplete_universe_does_not_replace_stocks(sessions, monkeypatch):
    monkeypatch.setattr("app.jobs.sync.level2_categories", lambda: ({"110100": {"code": "110100", "id": "bank_l2", "name": "银行细分", "parent_id": "bank"}}, {"bank_l2": {"code": "110100", "id": "bank_l2", "name": "银行细分", "parent_id": "bank"}}))
    provider = MetadataProvider()
    service = SyncService(provider, sessions)
    service.metadata("20260105", "20260106")
    provider.missing_exchange = True
    with pytest.raises(ProviderError):
        service.metadata("20260105", "20260106")
    with sessions() as s:
        assert len(list(s.scalars(select(Stock)))) == 3


