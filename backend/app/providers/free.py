"""Credential-free public data. AKShare handles exchange/SW formats;
Eastmoney transport retains timestamps and pagination totals omitted by AKShare's spot wrapper.
"""

import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from app.providers.tushare import ProviderError
from app.settings import ROOT, db_path

SOURCE = "免费公开数据 · 东方财富 / AKShare"
TZ = ZoneInfo("Asia/Shanghai")


def free_cutoff():
    now = datetime.now(TZ)
    return (
        now.date() if (now.hour, now.minute) >= (15, 30) else now.date() - timedelta(days=1)
    ).strftime("%Y%m%d")


def date_text(value):
    value = str(value or "")[:10].replace("-", "")
    try:
        datetime.strptime(value, "%Y%m%d")
    except ValueError:
        raise ProviderError("数据源上市/交易日期格式无效") from None
    return value


def numeric(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def positive(value):
    value = numeric(value)
    return value if value is not None and value > 0 else None


def nonnegative(value):
    value = numeric(value)
    return value if value is not None and value >= 0 else None


def history_candle(date, open_value, high_value, low_value, close_value, volume_value):
    values = [numeric(value) for value in (open_value, high_value, low_value, close_value)]
    if any(value is None or value <= 0 for value in values):
        raise ProviderError("历史 K 线缺少有效开高低收价格")
    opened, high, low, close = values
    if low > min(opened, close) or high < max(opened, close) or low > high:
        raise ProviderError("历史 K 线开高低收价格关系异常")
    volume = numeric(volume_value)
    if volume is None or volume < 0:
        raise ProviderError("历史 K 线缺少有效成交量")
    return {
        "date": date_text(date),
        "open": opened,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def stock_code(symbol):
    symbol = str(symbol).zfill(6)
    if not re.fullmatch(r"\d{6}", symbol):
        raise ProviderError("股票代码格式无效")
    if symbol.startswith("6"):
        return symbol + ".SH"
    if symbol.startswith(("0", "3")):
        return symbol + ".SZ"
    if symbol.startswith(("4", "8", "92")):
        return symbol + ".BJ"
    raise ProviderError(f"非 A 股代码：{symbol}")


class FreeProvider:
    def __init__(self, client=None, interval=None, cache_dir=None):
        self.client = client or httpx.Client(timeout=25, follow_redirects=True)
        self.interval = (
            float(os.getenv("FREE_MIN_INTERVAL", "0.35")) if interval is None else interval
        )
        self.last_call = 0.0
        self.snapshot_source = SOURCE
        self.warnings = []
        self.history_channel = "东方财富"
        self.cache = cache_dir or db_path().parent / "free-cache"
        self.cache.mkdir(parents=True, exist_ok=True)

    def close(self):
        self.client.close()

    def throttle(self):
        time.sleep(max(0, self.interval - (time.monotonic() - self.last_call)))
        self.last_call = time.monotonic()

    def ak(self, name, **params):
        # Reuse same-day successful metadata after an interrupted run, never cache failures.
        key = hashlib.sha256(json.dumps([name, params], sort_keys=True).encode()).hexdigest()
        path = self.cache / f"{datetime.now(TZ):%Y%m%d}-{key}.json"
        if path.exists():
            return json.loads(path.read_text())
        for attempt in range(2):
            self.throttle()
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "app.providers.ak_worker"],
                    input=json.dumps({"name": name, "params": params}),
                    capture_output=True,
                    text=True,
                    timeout=90,
                    cwd=ROOT / "backend",
                )
                if result.returncode:
                    raise ProviderError(
                        f"AKShare {name} 返回异常，请运行 doctor 检查网络与上游接口"
                    )
                rows = json.loads(result.stdout)
                if not isinstance(rows, list) or not rows:
                    raise ProviderError(f"AKShare {name} 返回空数据")
                temp = path.with_suffix(".tmp")
                temp.write_text(json.dumps(rows, ensure_ascii=False))
                temp.replace(path)
                return rows
            except (subprocess.TimeoutExpired, ValueError, ProviderError) as exc:
                if attempt:
                    raise ProviderError(f"{name} 失败（已重试）：{exc}") from None
                time.sleep(1)

    def request(self, url, params):
        for attempt in range(3):
            self.throttle()
            try:
                response = self.client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                if data.get("rc") != 0 or data.get("data") is None:
                    raise ProviderError("东方财富返回空数据或错误状态")
                return data["data"]
            except (httpx.HTTPError, ValueError, ProviderError) as exc:
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (
                    401,
                    403,
                ):
                    raise ProviderError(
                        f"公开接口拒绝访问（HTTP {exc.response.status_code}），未尝试绕过限制"
                    ) from None
                if attempt == 2:
                    raise ProviderError(
                        f"东方财富接口失败（已重试）：{type(exc).__name__}"
                    ) from None
                time.sleep(2**attempt)

    def universe(self):
        result = []
        for api, params, exchange, board, code_key, name_key, date_key in [
            (
                "stock_info_sh_name_code",
                {"symbol": "主板A股"},
                "SSE",
                "沪市主板",
                "证券代码",
                "证券简称",
                "上市日期",
            ),
            (
                "stock_info_sh_name_code",
                {"symbol": "科创板"},
                "SSE",
                "科创板",
                "证券代码",
                "证券简称",
                "上市日期",
            ),
            (
                "stock_info_sz_name_code",
                {"symbol": "A股列表"},
                "SZSE",
                None,
                "A股代码",
                "A股简称",
                "A股上市日期",
            ),
            ("stock_info_bj_name_code", {}, "BSE", "北交所", "证券代码", "证券简称", "上市日期"),
        ]:
            rows = self.ak(api, **params)
            for row in rows:
                code = stock_code(row[code_key])
                if not code.endswith({"SSE": ".SH", "SZSE": ".SZ", "BSE": ".BJ"}[exchange]):
                    raise ProviderError("交易所股票名单包含未知代码格式")
                result.append(
                    dict(
                        ts_code=code,
                        symbol=code[:6],
                        name=row[name_key],
                        fullname=row.get("公司全称"),
                        exchange=exchange,
                        board=board or ("创业板" if row.get("板块") == "创业板" else "深市主板"),
                        list_date=date_text(row[date_key]),
                    )
                )
        if len({r["ts_code"] for r in result}) != len(result):
            raise ProviderError("交易所名单包含重复股票")
        return result

    def industries(self):
        rows = self.ak("index_realtime_sw", symbol="一级行业")
        result = []
        for row in rows:
            code = str(row["指数代码"])
            if not re.fullmatch(r"801\d{3}", code):
                raise ProviderError("SW2021 一级行业代码异常")
            result.append({"id": code + ".SI", "name": row["指数名称"]})
        # SW2021's 31 industries distinguish it from the old 28-industry universe.
        if len(result) != 31 or len({r["id"] for r in result}) != 31:
            raise ProviderError("SW2021 行业数量/版本发生变化，需核对 SW2021 后再导入")
        return result

    def members(self, industry):
        rows = self.ak("index_component_sw", symbol=industry[:6])
        if len(rows) >= 10000:
            raise ProviderError("SW2021 成分达到接口上限，可能截断")
        codes = [stock_code(r["证券代码"]) for r in rows]
        if len(set(codes)) != len(codes):
            raise ProviderError("SW2021 成分重复")
        return codes

    def classification_history(self):
        return self.ak("stock_industry_clf_hist_sw")

    def calendar(self):
        dates = [date_text(r["trade_date"]) for r in self.ak("tool_trade_date_hist_sina")]
        if len(set(dates)) != len(dates):
            raise ProviderError("交易日历重复")
        return sorted(dates)

    def snapshot(self):
        try:
            rows = self.eastmoney_snapshot()
            self.snapshot_source = SOURCE
            return rows
        except ProviderError as exc:
            self.warnings.append(f"东方财富全市场行情暂不可用，使用腾讯公开行情：{exc}")
            self.snapshot_source = "免费公开数据 · 腾讯 / AKShare"
            return self.tencent_snapshot([r["ts_code"] for r in self.universe()])

    def tencent_snapshot(self, codes):
        result = []
        for offset in range(0, len(codes), 80):
            batch = codes[offset : offset + 80]
            symbols = [{"SH": "sh", "SZ": "sz", "BJ": "bj"}[c[-2:]] + c[:6] for c in batch]
            response = None
            for attempt in range(3):
                self.throttle()
                try:
                    response = self.client.get("https://qt.gtimg.cn/q=" + ",".join(symbols))
                    response.raise_for_status()
                    break
                except httpx.HTTPError:
                    if attempt == 2:
                        raise ProviderError("腾讯公开行情网络异常（已重试）") from None
                    time.sleep(2**attempt)
            matches = re.findall(r'v_((?:sh|sz|bj)\d{6})="([^"\n]*)";', response.text)
            seen = set()
            for symbol, body in matches:
                if symbol not in symbols or symbol in seen:
                    raise ProviderError("腾讯行情批次代码不符或重复")
                seen.add(symbol)
                fields = body.split("~")
                if len(fields) < 58 or fields[2] != symbol[2:]:
                    raise ProviderError("腾讯行情字段结构发生变化")
                stamp = fields[30]
                if not re.fullmatch(r"\d{14}", stamp):
                    raise ProviderError("腾讯行情缺少源时间戳")
                amount, cap = numeric(fields[57]), positive(fields[45])
                float_cap = positive(fields[44])
                total_shares = positive(fields[73]) if len(fields) > 73 else None
                float_shares = positive(fields[72]) if len(fields) > 72 else None
                if float_cap and cap and float_cap > cap * 1.02:
                    float_cap = None
                if float_shares and total_shares and float_shares > total_shares * 1.02:
                    float_shares = None
                result.append(
                    dict(
                        ts_code=stock_code(fields[2]),
                        name=fields[1],
                        close=numeric(fields[3]),
                        pre_close=positive(fields[4]),
                        open=positive(fields[5]),
                        high=positive(fields[33]),
                        low=positive(fields[34]),
                        volume=nonnegative(fields[36]),
                        pct_chg=numeric(fields[32]),
                        amount=amount * 10000 if amount is not None else None,
                        market_cap=round(cap * 100000000) if cap is not None else None,
                        float_market_cap=round(float_cap * 100000000) if float_cap else None,
                        turnover_rate=nonnegative(fields[38]),
                        pe_ratio=positive(fields[39]),
                        pe_basis="行情源口径",
                        pb_ratio=positive(fields[46]),
                        total_shares=total_shares,
                        float_shares=float_shares,
                        date=stamp[:8],
                        time=stamp[8:],
                    )
                )
            # Empty per-symbol responses are represented as missing by the service.
            if not matches:
                raise ProviderError("腾讯行情整批为空，拒绝发布")
        return result

    def eastmoney_snapshot(self):
        rows, seen, total = [], set(), None
        for page in range(1, 201):
            data = self.request(
                "https://push2.eastmoney.com/api/qt/clist/get",
                {
                    "pn": page,
                    "pz": 100,
                    "po": 0,
                    "np": 1,
                    "fltt": 2,
                    "fid": "f12",
                    "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
                    "fields": "f12,f13,f14,f2,f3,f5,f6,f8,f9,f15,f16,f17,f18,f20,f21,f23,f124",
                },
            )
            count = int(data["total"])
            if total is not None and count != total:
                raise ProviderError("行情分页期间股票总数变化，请重试")
            total = count
            batch = data.get("diff") or []
            if isinstance(batch, dict):
                batch = list(batch.values())
            if not batch:
                raise ProviderError("行情分页提前结束，拒绝发布截断结果")
            for r in batch:
                code = stock_code(r["f12"])
                if code in seen:
                    raise ProviderError("行情分页重复，拒绝发布")
                seen.add(code)
                stamp = numeric(r.get("f124"))
                at = datetime.fromtimestamp(stamp, TZ) if stamp else None
                rows.append(
                    dict(
                        ts_code=code,
                        name=r["f14"],
                        close=numeric(r.get("f2")),
                        pre_close=positive(r.get("f18")),
                        open=positive(r.get("f17")),
                        high=positive(r.get("f15")),
                        low=positive(r.get("f16")),
                        volume=nonnegative(r.get("f5")),
                        pct_chg=numeric(r.get("f3")),
                        amount=numeric(r.get("f6")),
                        market_cap=numeric(r.get("f20")),
                        float_market_cap=positive(r.get("f21")),
                        turnover_rate=nonnegative(r.get("f8")),
                        pe_ratio=positive(r.get("f9")),
                        pe_basis="动态",
                        pb_ratio=positive(r.get("f23")),
                        total_shares=None,
                        float_shares=None,
                        date=at.strftime("%Y%m%d") if at else None,
                        time=at.strftime("%H%M%S") if at else None,
                    )
                )
            if len(rows) == total:
                return rows
            if len(rows) > total:
                raise ProviderError("行情数量超过接口总数")
        raise ProviderError("行情分页超过上限")

    def history(self, symbol, start, end, adjusted=False):
        # Bounded yearly requests avoid silent server-side truncation.
        result = []
        cursor = start
        while cursor <= end:
            year_end = min(end, cursor[:4] + "1231")
            result.extend(self._history_year(symbol, cursor, year_end, adjusted))
            cursor = str(int(cursor[:4]) + 1) + "0101"
        return result

    def _history_year(self, symbol, start, end, adjusted=False):
        data = self.request(
            "https://push2his.eastmoney.com/api/qt/stock/kline/get",
            {
                "secid": f"{1 if symbol.startswith('6') else 0}.{symbol}",
                "klt": 101,
                # hfq is positive even when qfq prices for very old bars become negative.
                "fqt": 2 if adjusted else 0,
                "beg": start,
                "end": end,
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            },
        )
        if data.get("code") != symbol:
            raise ProviderError("历史接口返回股票代码不符")
        result = []
        for line in data.get("klines") or []:
            fields = line.split(",")
            if len(fields) < 6:
                raise ProviderError("历史 K 线字段不完整")
            candle = history_candle(
                fields[0], fields[1], fields[3], fields[4], fields[2], fields[5]
            )
            if not start <= candle["date"] <= end:
                raise ProviderError("历史价格/日期异常")
            result.append(candle)
        if len({r["date"] for r in result}) != len(result):
            raise ProviderError("历史价格日期重复")
        if len(result) >= 1000:
            raise ProviderError("历史接口可能截断，未发布结果")
        return result

    def profile(self, symbol):
        row = self.ak("stock_profile_cninfo", symbol=symbol)[0]
        return {
            "fullname": row.get("公司名称"),
            "introduction": row.get("机构简介"),
            "main_business": row.get("主营业务"),
        }

    def tencent_history(self, symbol, start, end, adjusted=False):
        result = {}
        cursor = ""
        for _ in range(12):
            rows = self._tencent_history_page(symbol, start, end, adjusted, cursor)
            if not rows:
                break
            earliest = min(r["date"] for r in rows)
            if cursor and earliest >= cursor.replace("-", ""):
                raise ProviderError("腾讯历史分页没有向前推进")
            result.update({r["date"]: r for r in rows})
            if earliest <= start or len(rows) < 600:
                break
            cursor = f"{earliest[:4]}-{earliest[4:6]}-{earliest[6:]}"
        else:
            raise ProviderError("腾讯历史分页超过安全上限")
        return [result[d] for d in sorted(result)]

    def _tencent_history_page(self, symbol, start, end, adjusted=False, cursor=""):

        code = stock_code(symbol)
        prefix = {"SH": "sh", "SZ": "sz", "BJ": "bj"}[code[-2:]]
        ticker = prefix + symbol
        for attempt in range(3):
            self.throttle()
            try:
                # A nonempty end parameter omits the current session on Tencent.
                # Request recent 640 bars, then apply the exact range locally.
                response = self.client.get(
                    "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get",
                    params={"param": f"{ticker},day,,{cursor},640,{'hfq' if adjusted else ''}"},
                )
                response.raise_for_status()
                payload = response.json()
                if payload.get("code") != 0:
                    raise ProviderError("腾讯历史接口返回错误状态")
                data = payload["data"][ticker]
                bars = data.get("hfqday", data.get("day")) if adjusted else data.get("day")
                if not bars:
                    raise ProviderError("腾讯历史为空")
                result = []
                for row in bars:
                    if len(row) < 6:
                        raise ProviderError("腾讯历史 K 线字段不完整")
                    date = date_text(row[0])
                    if start <= date <= end:
                        result.append(history_candle(date, row[1], row[3], row[4], row[2], row[5]))
                if not result or len({r["date"] for r in result}) != len(result):
                    raise ProviderError("腾讯历史为空或日期重复")
                return result
            except (httpx.HTTPError, ValueError, KeyError, ProviderError) as exc:
                if attempt == 2:
                    raise ProviderError(
                        f"腾讯历史接口失败（已重试）：{type(exc).__name__}"
                    ) from None
                time.sleep(2**attempt)

    def history_pair(self, symbol, start, end):
        if self.history_channel == "东方财富":
            try:
                adjusted = self.history(symbol, start, end, adjusted=True)
                raw = self.history(symbol, start, end)
                return raw, adjusted
            except ProviderError:
                self.history_channel = "腾讯"
                self.warnings.append(
                    "东方财富历史通道不可用，本次后续回填改用腾讯；原始与复权价格始终成对获取。"
                )
        adjusted = self.tencent_history(symbol, start, end, adjusted=True)
        raw = self.tencent_history(symbol, start, end)
        return raw, adjusted

    def doctor(self):
        checks, failures = {}, []
        recent = (datetime.strptime(free_cutoff(), "%Y%m%d") - timedelta(days=30)).strftime(
            "%Y%m%d"
        )
        for name, call in [
            ("沪深北股票名单", self.universe),
            ("SW2021 一级行业", self.industries),
            ("SW2021 银行成分", lambda: self.members("801780.SI")),
            ("SW2021 官方分类历史", self.classification_history),
            ("交易日历", self.calendar),
            ("全市场行情", self.snapshot),
            *[
                (
                    f"历史 {code}",
                    lambda code=code: self.history_pair(code, recent, free_cutoff())[0],
                )
                for code in ("600519", "000001", "920000")
            ],
        ]:
            try:
                checks[name] = {"ok": True, "rows": len(call())}
            except Exception as exc:
                checks[name] = {"ok": False, "error": str(exc)}
                failures.append(name)
        return {
            "source": self.snapshot_source,
            "history_source": self.history_channel,
            "ok": not failures,
            "checks": checks,
            "warnings": self.warnings,
        }
