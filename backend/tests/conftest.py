import pytest
from app.api import database, router
from app.db import make_engine
from app.models import (
    Base,
    Calendar,
    CodeAlias,
    Factor,
    Industry,
    Publication,
    Quote,
    Representative,
    Stock,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def sessions(tmp_path, monkeypatch):
    # Maintenance locks and caches must be isolated along with the fixture database.
    monkeypatch.setenv("STOCK_DB_PATH", str(tmp_path / "test.sqlite3"))
    engine = make_engine(tmp_path / "test.sqlite3")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    yield factory
    engine.dispose()


@pytest.fixture
def seeded(sessions):
    with sessions.begin() as s:
        s.add_all([Industry(id="bank", name="银行"), Industry(id="tech", name="电子")])
        s.flush()
        for i, name, industry, pct, status in [
            (1, "甲银行", "bank", 2.5, "trading"),
            (2, "乙银行", "bank", -3.0, "trading"),
            (3, "停牌银行", "bank", None, "suspended"),
            (4, "科技公司", "tech", 2.5, "trading"),
        ]:
            s.add(
                Stock(
                    id=i,
                    ts_code=f"{i:06d}.SZ",
                    symbol=f"{i:06d}",
                    name=name,
                    exchange="SZSE",
                    board="深市主板",
                    list_date="20200101",
                    industry_id=industry,
                )
            )
        s.flush()
        for i, pct, state in [
            (1, 2.5, "trading"),
            (2, -3.0, "trading"),
            (3, None, "suspended"),
            (4, 2.5, "trading"),
        ]:
            s.add(CodeAlias(code=f"{i:06d}.SZ", stock_id=i))
            s.add(
                Quote(
                    stock_id=i,
                    trade_date="20260105",
                    open=None if state == "suspended" else 9.5,
                    high=None if state == "suspended" else 11,
                    low=None if state == "suspended" else 9,
                    close=None if state == "suspended" else 10,
                    volume=None if state == "suspended" else 1000,
                    pct_chg=pct,
                    amount=10000,
                    market_cap=None if i == 3 else 1000000 * i,
                    status=state,
                )
            )
            s.add(Factor(stock_id=i, trade_date="20260105", value=2))
        s.add(
            Representative(
                stock_id=1,
                industry_id="bank",
                position=0,
                reason="测试说明",
                source_url="https://example.org",
                reviewed_at="2026-01-05",
            )
        )
        s.add(Publication(trade_date="20260105", stock_count=4))
        s.add(Calendar(exchange="SZSE", date="20260105", is_open=True, source="fixture"))
    return sessions


@pytest.fixture
def client(seeded):
    app = FastAPI()
    app.include_router(router)

    def db():
        with seeded() as s:
            yield s

    app.dependency_overrides[database] = db
    with TestClient(app) as c:
        yield c
