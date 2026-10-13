from app.jobs.leaders import SOURCE_URL, ranked_components, refresh_index_leaders
from app.models import Industry, Representative, RepresentativeL2, Stock
from app.providers.tushare import ProviderError
from sqlalchemy import select


def component(code, weight):
    return {"证券代码": code, "最新权重": weight}


def test_index_weight_replaces_manual_candidates_and_orders_leaders(seeded):
    class Source:
        def ak(self, name, **params):
            if name == "index_realtime_sw":
                return [{"指数代码": "801016"}]
            return {
                "bank": [component("000001", 30), component("000002", 70)],
                "tech": [component("000004", 100)],
                "801016": [component("000001", 100)],
            }[params["symbol"]]

    with seeded.begin() as session:
        session.add(Industry(id="801016.SI", name="银行细分", level=2, parent_id="bank"))
        session.get(Stock, 1).industry_l2_id = "801016.SI"

    result = refresh_index_leaders(Source(), seeded)
    assert result["level1"] == 3
    assert result["level2"] == 1
    with seeded() as session:
        leaders = list(
            session.scalars(
                select(Representative)
                .where(Representative.industry_id == "bank")
                .order_by(Representative.position)
            )
        )
        assert [leader.stock_id for leader in leaders] == [2, 1]
        assert "70.00%" in leaders[0].reason
        assert leaders[0].source_url == SOURCE_URL + "bank"
        assert session.get(RepresentativeL2, 1).source_url == SOURCE_URL + "801016"


def test_source_failure_removes_manual_list_but_preserves_official_result(seeded):
    with seeded.begin() as session:
        session.add(
            Representative(
                stock_id=2,
                industry_id="bank",
                position=0,
                reason="已验证权重",
                source_url=SOURCE_URL + "bank",
                reviewed_at="2026-10-09",
            )
        )

    class Source:
        def ak(self, name, **params):
            if name == "index_realtime_sw":
                return [{"指数代码": "801016"}]
            if params["symbol"] == "bank":
                raise ProviderError("暂不可用")
            return [component("000004", 100)]

    result = refresh_index_leaders(Source(), seeded)
    assert any("暂不可用" in warning for warning in result["warnings"])
    with seeded() as session:
        leaders = list(session.scalars(select(Representative).where(Representative.industry_id == "bank")))
        assert [leader.stock_id for leader in leaders] == [2]


def test_retired_secondary_index_does_not_keep_old_leaders(seeded):
    with seeded.begin() as session:
        session.add(Industry(id="801016.SI", name="银行细分", level=2, parent_id="bank"))
        session.get(Stock, 1).industry_l2_id = "801016.SI"
        session.add(
            RepresentativeL2(
                stock_id=1,
                industry_id="801016.SI",
                position=0,
                reason="旧权重",
                source_url=SOURCE_URL + "801016",
                reviewed_at="2026-10-09",
            )
        )

    class Source:
        def ak(self, name, **params):
            if name == "index_realtime_sw":
                return []
            return {
                "bank": [component("000001", 30), component("000002", 70)],
                "tech": [component("000004", 100)],
            }[params["symbol"]]

    result = refresh_index_leaders(Source(), seeded)
    assert result["industries_without_index"] == 1
    with seeded() as session:
        assert session.get(RepresentativeL2, 1) is None


def test_incomplete_weights_rejected():
    try:
        ranked_components([component("000001", 45), component("000002", 40)])
    except ProviderError as exc:
        assert "100%" in str(exc)
    else:
        raise AssertionError("incomplete constituent weights must be rejected")
