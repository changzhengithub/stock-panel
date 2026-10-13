import pytest
from app.industry import level2_categories, official_assignments
from app.providers.tushare import ProviderError


def test_sw2021_level2_catalog_has_complete_unique_hierarchy():
    by_code, by_id = level2_categories()
    assert len(by_code) == len(by_id) == 134
    assert len({row["parent_id"] for row in by_code.values()}) == 31


def test_official_assignments_use_latest_history_and_check_parent():
    category = level2_categories()[0]["110100"]
    old = dict(symbol="600001", industry_code="220200", start_date="2021-01-01", update_time="2021-01-01")
    current = dict(symbol="600001", industry_code="110100", start_date="2026-01-01", update_time="2026-01-02")
    history = [old] * 10_000 + [current]
    stocks = [dict(ts_code="600001.SH")]
    assigned, changed, count = official_assignments(
        history, stocks, {"600001.SH": category["parent_id"]}
    )
    assert assigned["600001.SH"] == category
    assert changed == "2026-01-02" and count == 1
    with pytest.raises(ProviderError, match="冲突"):
        official_assignments(history, stocks, {"600001.SH": "801030.SI"})
    with pytest.raises(ProviderError, match="覆盖不足"):
        official_assignments(history, stocks + [dict(ts_code="000001.SZ")], {})
