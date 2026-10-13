"""Isolate AKShare calls so missing upstream timeouts cannot hang the sync lock."""

import contextlib
import io
import json
import sys
import warnings

import pandas as pd
import requests
import urllib3


def official_sw_history(ak):
    try:
        return ak.stock_industry_clf_hist_sw()
    except requests.exceptions.SSLError:
        # This public SW host sometimes omits an intermediate certificate. The
        # isolated fallback sends no credentials; the caller validates every row.
        url = "https://www.swsresearch.com/swindex/pdf/SwClass2021/StockClassifyUse_stock.xls"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)
            response = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.swsresearch.com/"},
                timeout=60,
                verify=False,
            )
        response.raise_for_status()
        if len(response.content) < 100_000 or not response.content.startswith((b"PK", b"\xd0\xcf")):
            raise ValueError("SW2021 官方分类文件不是完整的 Excel 文件")
        frame = pd.read_excel(
            io.BytesIO(response.content), dtype={"股票代码": str, "行业代码": str}
        )
        frame.rename(
            columns={
                "股票代码": "symbol",
                "计入日期": "start_date",
                "行业代码": "industry_code",
                "更新日期": "update_time",
            },
            inplace=True,
        )
        return frame


def main():
    import akshare as ak

    payload = json.loads(sys.stdin.read())
    allowed = {
        "stock_info_sh_name_code",
        "stock_info_sz_name_code",
        "stock_info_bj_name_code",
        "index_realtime_sw",
        "index_component_sw",
        "index_hist_sw",
        "tool_trade_date_hist_sina",
        "stock_profile_cninfo",
        "stock_industry_clf_hist_sw",
        "stock_board_concept_name_em",
        "stock_board_concept_cons_em",
    }
    name = payload["name"]
    if name not in allowed:
        raise ValueError("Unsupported AKShare function")
    with contextlib.redirect_stdout(sys.stderr):
        df = (
            official_sw_history(ak)
            if name == "stock_industry_clf_hist_sw"
            else getattr(ak, name)(**payload["params"])
        )
    # pandas JSON normalizes dates, numpy numbers and NaN without non-standard JSON.
    print(df.to_json(orient="records", force_ascii=False, date_format="iso"))


if __name__ == "__main__":
    main()
