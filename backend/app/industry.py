"""Validate the published SW2021 hierarchy against current stock assignments."""

import json
import re
from functools import lru_cache

from app.providers.tushare import ProviderError
from app.settings import ROOT


@lru_cache(maxsize=1)
def level2_categories():
    payload = json.loads((ROOT / "config/sw2021-l2.json").read_text())
    rows = payload["industries"]
    by_code = {row["code"]: row for row in rows}
    by_id = {row["id"]: row for row in rows}
    if (
        len(rows) != 134
        or len(by_code) != len(rows)
        or len(by_id) != len(rows)
        or len({row["parent_id"] for row in rows}) != 31
        or any(
            not re.fullmatch(r"\d{4}00", row["code"])
            or not re.fullmatch(r"801\d{3}\.SI", row["id"])
            or not row["name"].strip()
            for row in rows
        )
    ):
        raise ProviderError("本地 SW2021 二级分类表无效，停止元数据更新")
    return by_code, by_id


def official_assignments(history, stocks, level1_membership):
    """Choose the latest official row per symbol, without guessing missing classes."""
    by_code, _ = level2_categories()
    if len(history) < 10000:
        raise ProviderError("SW2021 官方分类历史记录明显不完整，停止元数据更新")
    latest = {}
    source_updated_at = None
    for row in history:
        symbol = str(row.get("symbol", ""))
        code = str(row.get("industry_code", ""))
        start = str(row.get("start_date", ""))[:10]
        updated = str(row.get("update_time", ""))[:10]
        if not re.fullmatch(r"\d{6}", symbol + "") or not re.fullmatch(r"\d{6}", code):
            raise ProviderError("SW2021 官方分类文件包含无效股票或行业代码")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", start) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}", updated
        ):
            raise ProviderError("SW2021 官方分类文件包含无效日期")
        source_updated_at = max(source_updated_at or updated, updated)
        prior = latest.get(symbol)
        key = (start, updated)
        if prior is None or key > prior[0]:
            latest[symbol] = (key, code)
        elif key == prior[0] and code != prior[1]:
            raise ProviderError(f"SW2021 官方分类文件中 {symbol} 的当前归属冲突")

    assignments = {}
    matched = 0
    for stock in stocks:
        symbol = stock["ts_code"][:6]
        code = stock["ts_code"]
        record = latest.get(symbol)
        if not record:
            assignments[code] = None
            continue
        category = by_code.get(record[1][:4] + "00")
        if not category:
            raise ProviderError(f"{code} 使用尚未维护的 SW2021 二级行业代码 {record[1]}")
        current_l1 = level1_membership.get(code)
        if current_l1 and current_l1 != category["parent_id"]:
            raise ProviderError(f"{code} 官方二级分类与当前 SW2021 一级成分冲突")
        assignments[code] = category
        matched += 1
    if not stocks or matched / len(stocks) < 0.99:
        raise ProviderError(f"SW2021 官方二级归属覆盖不足 99%（{matched}/{len(stocks)}），保留旧分类")
    return assignments, source_updated_at, matched
