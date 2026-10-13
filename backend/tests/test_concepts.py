import pytest
from app.jobs.concepts import sync_concepts
from app.jobs.concepts_tdx import sync_tdx_concepts
from app.models import Concept, ConceptMember
from app.providers.tushare import ProviderError


def test_concept_filter_uses_same_stock_list_and_intersects_market(client, seeded):
    with seeded.begin() as session:
        session.add(Concept(id="BK1234", name="固态电池", source="fixture", fetched_at="2026-01-05"))
        session.add_all(
            [ConceptMember(concept_id="BK1234", stock_id=1), ConceptMember(concept_id="BK1234", stock_id=4)]
        )
    catalog = client.get("/api/concepts").json()
    assert catalog[0]["name"] == "固态电池" and catalog[0]["stock_count"] == 2
    result = client.get("/api/stocks", params={"concept_id": "BK1234", "sort": "pct_desc"})
    assert result.status_code == 200
    assert {stock["id"] for stock in result.json()["items"]} == {1, 4}
    assert client.get("/api/stocks", params={"concept_id": "BK1234", "industry_id": "bank"}).json()["total"] == 1
    assert client.get("/api/stocks", params={"concept_id": "BK1234", "scope": "representatives"}).status_code == 422
    assert client.get("/api/stocks", params={"concept_id": "missing"}).status_code == 422
    summary = client.get("/api/industry-summary", params={"concept_id": "BK1234"}).json()
    assert summary["total"] == 2 and summary["index"] is None


def test_concept_sync_keeps_last_valid_members_on_failure(seeded):
    class Provider:
        fail = False

        def ak(self, name, **params):
            if name == "stock_board_concept_name_em":
                return [{"板块代码": "BK1234", "板块名称": "固态电池"}]
            if self.fail:
                raise RuntimeError("上游暂不可用")
            return [{"代码": "000001"}, {"代码": "000004"}]

    provider = Provider()
    assert sync_concepts(provider, sessions=seeded, minimum_catalog_size=1)["updated"] == 1
    with seeded() as session:
        assert {member.stock_id for member in session.query(ConceptMember)} == {1, 4}
    provider.fail = True
    result = sync_concepts(provider, sessions=seeded, minimum_catalog_size=1)
    assert result["updated"] == 0 and len(result["failures"]) == 1
    with seeded() as session:
        assert {member.stock_id for member in session.query(ConceptMember)} == {1, 4}
        assert session.get(Concept, "BK1234").fetched_at is not None


def test_unsynced_concept_reports_failed_source(client, seeded):
    with seeded.begin() as session:
        session.add(
            Concept(
                id="BK0968",
                name="固态电池",
                source="fixture",
                error="上游连接已断开",
            )
        )
    response = client.get("/api/stocks", params={"concept_id": "BK0968"})
    assert response.status_code == 503
    assert "固态电池成分同步失败" in response.json()["detail"]


def test_tdx_snapshot_publishes_valid_members_and_skips_capped_boards(seeded):
    class Block:
        def __init__(self, name, codes):
            self.name, self.codes, self.count = name, codes, len(codes)

    result = sync_tdx_concepts(
        sessions=seeded, minimum_catalog_size=1,
        blocks=[Block("固态电池", ["000001", "000004"]), Block("大板块", [f"{i:06d}" for i in range(400)])],
    )
    assert result["updated"] == 1 and result["limited"] == ["大板块"]
    with seeded() as session:
        board = session.get(Concept, "TDX:固态电池")
        assert board.name == "固态电池" and board.fetched_at
        assert {member.stock_id for member in session.query(ConceptMember).filter_by(concept_id=board.id)} == {1, 4}
        assert session.get(Concept, "TDX:大板块") is not None

    with pytest.raises(ProviderError, match="匹配不足"):
        sync_tdx_concepts(
            sessions=seeded, minimum_catalog_size=1,
            blocks=[Block("固态电池", ["999999"])],
        )
    with seeded() as session:
        assert {member.stock_id for member in session.query(ConceptMember).filter_by(concept_id="TDX:固态电池")} == {1, 4}
