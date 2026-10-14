from types import SimpleNamespace

import pytest
from app.business_analysis import (
    analysis_rules,
    assert_rule_coverage,
    audit_analysis,
    enrich_operating_analysis,
    explain_company,
)
from app.jobs.chain_supplement import recipes


def document():
    return {
        "nodes": [
            {"key": f"n{i}", "name": name, "column": i, "variable": "实际业务量", "evidence": []}
            for i, name in enumerate(["投入", "经营", "需求"])
        ],
        "edges": [{"key": "supply", "source": "n0", "target": "n1", "kind": "供给"}],
        "stocks": [],
    }


def enriched(name, parent):
    industry = SimpleNamespace(id="child", name=name, level=2, parent_id="parent")
    industries = {
        "child": industry,
        "parent": SimpleNamespace(id="parent", name=parent, parent_id=None, level=1),
    }
    return enrich_operating_analysis(document(), industry, industries)


def test_all_134_have_unique_operating_logic_and_full_rules_are_required():
    rules = analysis_rules()
    assert_rule_coverage(recipes())
    assert len(rules["sector_analysis"]) == 31
    assert len({row["经营逻辑"] for row in rules["business_logic"].values()}) == 134
    broken = recipes()
    broken["subindustries"] = {**broken["subindustries"], "尚未分析的测试行业": {}}
    with pytest.raises(ValueError, match="未覆盖全部行业"):
        assert_rule_coverage(broken)


@pytest.mark.parametrize(
    "name,parent,keyword",
    [
        ("股份制银行Ⅱ", "银行", "负债"),
        ("证券Ⅱ", "非银金融", "经纪"),
        ("保险Ⅱ", "非银金融", "承保"),
        ("软件开发", "计算机", "订阅"),
        ("普钢", "钢铁", "矿焦"),
        ("航空机场", "交通运输", "票价"),
        ("互联网电商", "商贸零售", "佣金"),
        ("种植业", "农林牧渔", "种植"),
        ("游戏Ⅱ", "传媒", "付费"),
    ],
)
def test_different_business_models_use_their_own_operating_and_cash_logic(name, parent, keyword):
    doc = enriched(name, parent)
    assert keyword in doc["nodes"][1]["analyses"][0]["mechanism"]
    assert "现金" in doc["nodes"][1]["analyses"][1]["horizon"]
    assert audit_analysis(doc)["passed"]
    assert doc["analysis_version"] == 2


def test_first_level_branches_use_each_child_logic():
    industry = SimpleNamespace(id="parent", name="非银金融", level=1, parent_id=None)
    children = [
        SimpleNamespace(id="a", name="证券Ⅱ", parent_id="parent"),
        SimpleNamespace(id="b", name="保险Ⅱ", parent_id="parent"),
    ]
    doc = document()
    doc["nodes"].insert(
        2, {"key": "insurance", "name": "保险Ⅱ", "column": 1, "variable": "保费", "evidence": []}
    )
    doc["nodes"][1]["name"] = "证券Ⅱ"
    result = enrich_operating_analysis(
        doc, industry, {"parent": industry, **{c.id: c for c in children}}
    )
    assert "经纪" in result["nodes"][1]["analyses"][0]["mechanism"]
    assert "承保" in result["nodes"][2]["analyses"][0]["mechanism"]


def test_company_explanation_does_not_turn_revenue_share_into_market_share():
    link = {
        "mapping_status": "业务词匹配",
        "metrics": [
            {"period": "2025-FY", "subject": "软件产品", "share": 70.0},
            {"period": "2026-H1", "subject": "软件产品", "share": 60.0},
        ],
        "leaders": [],
    }
    explanation = explain_company(link, ["软件"])
    assert any("2026-H1" in x for x in explanation)
    assert any("60.00%" in x and "不代表产业链市场份额" in x for x in explanation)
    assert any("年度与半年度" in x for x in explanation)
    assert link["leaders"] == []
    link["mapping_status"] = "分类候选"
    link["metrics"] = []
    assert "不能将分类归属当作业务事实" in explain_company(link, [])[0]


def test_analysis_audit_rejects_directory_only_and_unexplained_companies():
    doc = enriched("软件开发", "计算机")
    doc["nodes"][1]["analyses"] = []
    assert not audit_analysis(doc)["passed"]
    doc = enriched("软件开发", "计算机")
    doc["stocks"] = [{"company_analysis": []}]
    assert not audit_analysis(doc)["passed"]
