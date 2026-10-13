from app.models import (
    Calendar,
    Factor,
    Industry,
    IndustrySnapshot,
    Publication,
    Quote,
    RepresentativeL2,
    Stock,
)


def test_filters_and_stable_pagination(client):
    first = client.get(
        "/api/stocks", params={"scope": "all", "sort": "pct_desc", "page_size": 1}
    ).json()
    second = client.get(
        "/api/stocks",
        params={"scope": "all", "sort": "pct_desc", "page_size": 1, "page": 2},
    ).json()
    assert first["total"] == 3
    assert first["items"][0]["id"] == 1 and second["items"][0]["id"] == 4
    data = client.get(
        "/api/stocks", params={"scope": "all", "industry_id": "bank", "sort": "pct_asc"}
    ).json()
    assert [s["id"] for s in data["items"]] == [2, 1]
    assert (
        client.get("/api/stocks", params={"scope": "all", "keyword": "000002"}).json()["total"] == 1
    )


def test_exchange_board_and_industry_filters(client, seeded):
    with seeded.begin() as s:
        s.get(Stock, 1).exchange = "SSE"
        s.get(Stock, 1).board = "科创板"
        s.get(Stock, 4).exchange = "BSE"
        s.get(Stock, 4).board = "北交所"
    response = client.get("/api/stocks", params={"scope": "all", "exchange": "SSE", "industry_id": "bank"})
    assert [item["id"] for item in response.json()["items"]] == [1]
    response = client.get("/api/stocks", params={"scope": "representatives", "exchange": "SSE", "board": "科创板"})
    assert [item["id"] for item in response.json()["items"]] == [1]
    response = client.get("/api/stocks", params={"scope": "all", "exchange": "BSE"})
    assert [item["id"] for item in response.json()["items"]] == [4]
    response = client.get("/api/stocks", params={"scope": "all", "exchange": "SZSE", "board": "深市主板"})
    assert [item["id"] for item in response.json()["items"]] == [2, 3]
    assert client.get("/api/stocks", params={"exchange": "SSE", "board": "创业板"}).status_code == 422
    assert client.get("/api/stocks", params={"exchange": "UNKNOWN"}).status_code == 422


def test_industry_counts_follow_exchange(client, seeded):
    with seeded.begin() as s:
        s.add(Industry(id="bank_l2", name="银行细分", level=2, parent_id="bank"))
        s.add(IndustrySnapshot(id=1, source="fixture", fetched_at="2026-01-05T16:00:00+08:00", classified_count=2, stock_count=4))
        s.get(Stock, 1).exchange = "SSE"
        s.get(Stock, 1).industry_l2_id = "bank_l2"
        s.get(Stock, 2).industry_l2_id = "bank_l2"
        s.get(Stock, 3).list_status = "D"
        s.get(Stock, 4).exchange = "BSE"
        s.add(RepresentativeL2(
            stock_id=1, industry_id="bank_l2", position=0,
            reason="测试", source_url="https://example.org", reviewed_at="2026-01-05",
        ))

    for exchange, expected in [(None, (2, 1)), ("SSE", (1, 0)), ("SZSE", (1, 0)), ("BSE", (0, 1))]:
        params = {"exchange": exchange} if exchange else {}
        first = client.get("/api/industries", params=params)
        second = client.get("/api/industries", params={**params, "level": 2})
        assert first.status_code == second.status_code == 200
        l1 = {row["id"]: row for row in first.json()}
        l2 = {row["id"]: row for row in second.json()}
        # Empty categories remain visible; only their market-specific count changes.
        assert (l1["bank"]["stock_count"], l1["tech"]["stock_count"]) == expected
        assert l2["bank_l2"]["stock_count"] == expected[0]
        assert l2.get("unclassified-l2", {}).get("stock_count", 0) == expected[1]
        assert l1["bank"]["representative_count"] == (1 if exchange in (None, "SSE") else 0)
        assert l2["bank_l2"]["representative_count"] == l1["bank"]["representative_count"]
        total = client.get("/api/stocks", params={**params, "scope": "all"}).json()["total"]
        assert sum(row["stock_count"] for row in first.json()) == total
        assert sum(row["stock_count"] for row in second.json()) == total
    assert client.get("/api/industries", params={"exchange": "UNKNOWN"}).status_code == 422


def test_industry_counts_follow_board(client, seeded):
    with seeded.begin() as s:
        s.add(Industry(id="bank_l2", name="银行细分", level=2, parent_id="bank"))
        s.add(IndustrySnapshot(id=1, source="fixture", fetched_at="2026-01-05T16:00:00+08:00", classified_count=1, stock_count=4))
        s.get(Stock, 1).exchange = "SSE"
        s.get(Stock, 1).board = "科创板"
        s.get(Stock, 1).industry_l2_id = "bank_l2"
        s.get(Stock, 2).board = "创业板"
        s.get(Stock, 4).exchange = "BSE"
        s.get(Stock, 4).board = "北交所"
    for exchange, board, expected, missing in [
        ("SSE", "科创板", 1, 0), ("SSE", "沪市主板", 0, 0),
        ("SZSE", "创业板", 1, 1), ("SZSE", "深市主板", 1, 1),
        ("BSE", "北交所", 1, 1),
    ]:
        params = {"exchange": exchange, "board": board}
        for level in (1, 2):
            response = client.get("/api/industries", params={**params, "level": level})
            assert response.status_code == 200
            rows = response.json()
            assert sum(row["stock_count"] for row in rows) == expected
            if level == 2:
                assert sum(row["stock_count"] for row in rows if row["id"] == "unclassified-l2") == missing
        assert client.get("/api/stocks", params={**params, "scope": "all"}).json()["total"] == expected
    assert client.get("/api/industries", params={"exchange": "SSE", "board": "创业板"}).status_code == 422
    assert client.get("/api/industries", params={"board": "UNKNOWN"}).status_code == 422


def test_representatives_and_pending_groups(client):
    data = client.get("/api/stocks", params={"scope": "representatives", "group_by": "industry", "page_size": 8}).json()
    assert data["total"] == 2 and data["matched_stocks"] == 1
    assert len(data["groups"][0]["items"]) == 1
    assert data["groups"][1]["items"] == []
    assert (
        client.get("/api/stocks", params={"group_by": "industry", "scope": "all"}).status_code
        == 422
    )


def test_nulls_stay_last_and_suspension_preserved(client):
    data = client.get("/api/stocks", params={"scope": "all", "sort": "market_cap_desc"}).json()
    assert data["items"][-1]["id"] == 3 and data["items"][-1]["close"] is None
    assert client.get("/api/stocks/999").status_code == 404
    assert client.get("/api/stocks", params={"page_size": 101}).status_code == 422


def test_search_literal_percent(client):
    assert client.get("/api/stocks", params={"scope": "all", "keyword": "%"}).json()["total"] == 0


def test_stock_basics_in_list_and_detail(client, seeded):
    with seeded.begin() as session:
        quote = session.get(Quote, (1, "20260105"))
        quote.float_market_cap = 800000
        quote.turnover_rate = 2.5
        quote.pe_ratio = 12.3
        quote.pe_basis = "TTM"
        quote.pb_ratio = 1.8
        quote.total_shares = 100000
        quote.float_shares = 80000
    for stock in (
        client.get("/api/stocks", params={"scope": "all", "keyword": "000001"}).json()["items"][0],
        client.get("/api/stocks/1").json(),
    ):
        assert stock["float_market_cap"] == 800000
        assert stock["turnover_rate"] == 2.5
        assert stock["pe_ratio"] == 12.3
        assert stock["pe_basis"] == "TTM"
        assert stock["pb_ratio"] == 1.8
        assert stock["total_shares"] == 100000
        assert stock["float_shares"] == 80000


def test_adjustment_and_missing_history(client, seeded):
    with seeded.begin() as s:
        s.add_all(
            [
                Calendar(exchange="SZSE", date="20260102", is_open=True, source="fixture"),
                Calendar(exchange="SZSE", date="20251231", is_open=True, source="fixture"),
                Quote(
                    stock_id=1,
                    trade_date="20260102",
                    open=11,
                    high=13,
                    low=10,
                    close=12,
                    volume=1200,
                    pct_chg=1,
                    amount=100,
                    market_cap=1000,
                ),
                Factor(stock_id=1, trade_date="20260102", value=1),
                Publication(trade_date="20260102", stock_count=1),
            ]
        )
    one = client.get("/api/stocks/1/prices?range=1m").json()
    year = client.get("/api/stocks/1/prices?range=1y").json()
    assert one["points"][1] == {
        "status": "trading", "date": "20260102", "open": 5.5, "high": 6.5, "low": 5.0, "close": 6.0, "volume": 1200,
    }
    assert one["points"][0]["close"] is None and not one["complete"]
    assert one["basis_date"] == year["basis_date"] == "20260105"
    assert one["points"][-1]["close"] == 10


def test_missing_anchor_does_not_fake_price(client, seeded):
    with seeded.begin() as s:
        s.delete(s.get(Factor, (1, "20260105")))
    assert client.get("/api/stocks/1/prices").json()["points"] == []


def test_data_status(client):
    result = client.get("/api/data-status").json()
    assert result["stock_count"] == 4 and result["trade_date"] == "20260105"


def test_level2_filters_and_unclassified(client, seeded):
    with seeded.begin() as s:
        s.add(Industry(id="bank_l2", name="股份制银行", level=2, parent_id="bank"))
        s.add(IndustrySnapshot(id=1, source="fixture", fetched_at="2026-01-05T16:00:00+08:00", classified_count=1, stock_count=4))
        s.get(Stock, 1).industry_l2_id = "bank_l2"
        s.add(RepresentativeL2(
            stock_id=1, industry_id="bank_l2", position=0,
            reason="二级行业测试样本", source_url="https://example.org", reviewed_at="2026-01-05",
        ))
    response = client.get("/api/industries", params={"level": 2})
    assert response.status_code == 200, response.text
    level2 = response.json()
    assert any(row["id"] == "bank_l2" and row["parent_name"] == "银行" for row in level2)
    assert any(row["id"] == "bank_l2" and row["representative_count"] == 1 for row in level2)
    assert any(row["id"] == "unclassified-l2" and row["stock_count"] == 3 for row in level2)
    result = client.get("/api/stocks", params={"scope": "all", "industry_level": 2, "industry_id": "bank_l2"}).json()
    assert [row["id"] for row in result["items"]] == [1]
    assert result["items"][0]["industry_l2"] == "股份制银行"
    assert client.get("/api/stocks", params={"scope": "all", "industry_level": 2, "industry_id": "unclassified-l2"}).json()["total"] == 3
    assert client.get("/api/stocks", params={"scope": "all", "industry_level": 2, "industry_id": "bank"}).status_code == 422
    representatives = client.get("/api/stocks", params={"scope": "representatives", "industry_level": 2, "industry_id": "bank_l2"}).json()
    assert [row["id"] for row in representatives["items"]] == [1]
    assert representatives["items"][0]["representative"]["industry_level"] == 2
    assert client.get("/api/stocks/1").json()["representative"]["industry_level"] == 1
    assert client.get("/api/stocks/1", params={"industry_level": 2}).json()["representative"]["industry_level"] == 2
    assert client.get("/api/stocks", params={"scope": "representatives", "industry_level": 2, "industry_id": "unclassified-l2"}).json()["total"] == 0
    assert client.get("/api/stocks", params={"scope": "representatives", "industry_level": 2, "group_by": "industry"}).status_code == 422


def test_interrupted_run_does_not_stay_running(client, seeded, monkeypatch):
    from app.models import SyncRun

    with seeded.begin() as s:
        s.add(SyncRun(command="sync", state="running"))
    monkeypatch.setattr("app.api.sync_running", lambda: False)
    assert client.get("/api/data-status").json()["last_run"]["state"] == "interrupted"
