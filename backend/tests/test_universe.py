import pytest
from app.models import Industry, IndustrySnapshot, Publication, Quote, RepresentativeL2, Stock


@pytest.mark.parametrize(
    "changes,st_flag",
    [
        ({"name": "ST甲银行"}, None),
        ({"name": "*ST甲银行"}, False),
        ({"name": "s*st甲银行"}, None),
        ({"name": "甲银行退"}, None),
        ({"name": "退市甲银行"}, None),
        ({"list_status": "D"}, None),
        ({"list_status": "inactive"}, None),
        ({"delist_date": "20200102"}, None),
        ({}, True),
    ],
)
def test_exclusion_is_consistent_across_browsing(client, seeded, changes, st_flag):
    with seeded.begin() as s:
        stock = s.get(Stock, 1)
        for key, value in changes.items():
            setattr(stock, key, value)
        s.get(Quote, (1, "20260105")).is_st = st_flag
        s.add(Industry(id="bank_l2", name="银行细分", level=2, parent_id="bank"))
        s.add(
            IndustrySnapshot(
                id=1,
                source="test",
                fetched_at="2026-01-05T16:00:00+08:00",
                classified_count=1,
                stock_count=4,
            )
        )
        stock.industry_l2_id = "bank_l2"
        s.add(
            RepresentativeL2(
                stock_id=1,
                industry_id="bank_l2",
                position=0,
                reason="test",
                source_url="https://example.org",
                reviewed_at="2026-01-05",
            )
        )

    result = client.get("/api/stocks?page_size=1").json()
    assert result["total"] == 3 and result["items"][0]["id"] == 2
    assert client.get("/api/stocks?keyword=000001").json()["total"] == 0
    assert client.get("/api/search?keyword=000001").json() == []
    assert client.get("/api/search?keyword=jiayinhang").json() == []
    assert client.get("/api/stocks?codes=000001.SZ,000002.SZ").json()["total"] == 1
    assert client.get("/api/stocks?sort=pct_desc").json()["total"] == 2
    assert client.get("/api/stocks?scope=representatives").json()["total"] == 0
    assert client.get("/api/stocks?scope=representatives&industry_level=2").json()["total"] == 0
    groups = client.get("/api/stocks?scope=representatives&group_by=industry").json()
    assert groups["matched_stocks"] == 0
    bank = next(group for group in groups["groups"] if group["id"] == "bank")
    assert bank["stock_count"] == 2 and bank["items"] == []
    navigation = client.get("/api/stocks?neighbor_of=2").json()["navigation"]
    assert navigation == dict(previous_id=None, next_id=3, position=1, total=3)
    for level in (1, 2):
        rows = client.get(f"/api/industries?level={level}").json()
        assert sum(row["stock_count"] for row in rows) == 3
        assert sum(row["representative_count"] for row in rows) == 0
    summary = client.get("/api/industry-summary?industry_id=bank").json()
    assert (summary["total"], summary["up"], summary["down"], summary["missing"]) == (2, 0, 1, 1)
    assert client.get("/api/data-status").json()["stock_count"] == 3
    assert client.get("/api/stocks/1").status_code == 404
    assert client.get("/api/stocks/1/prices").status_code == 404
    # Ordinary suspension remains browsable.
    assert client.get("/api/stocks/3").status_code == 200


def test_name_filter_works_without_quote_or_publication(client, seeded):
    with seeded.begin() as s:
        s.get(Stock, 1).name = "*ST甲银行"
        s.delete(s.get(Quote, (1, "20260105")))
        s.delete(s.get(Publication, "20260105"))
    assert client.get("/api/stocks").json()["total"] == 3
    assert client.get("/api/search?keyword=000001").json() == []


def test_only_latest_published_st_flag_applies_and_removal_can_recover(client, seeded):
    with seeded.begin() as s:
        s.get(Quote, (1, "20260105")).is_st = True
    assert client.get("/api/stocks?keyword=000001").json()["total"] == 0
    with seeded.begin() as s:
        s.add(Publication(trade_date="20260106", stock_count=4))
        s.add(Quote(stock_id=1, trade_date="20260106", is_st=False))
        # An unpublished future flag must not change the published browsing universe.
        s.add(Quote(stock_id=1, trade_date="20260107", is_st=True))
    assert client.get("/api/stocks?keyword=000001").json()["total"] == 1
    assert client.get("/api/search?keyword=000001").json()[0]["id"] == 1
