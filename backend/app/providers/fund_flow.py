"""Source-scoped Eastmoney fund flows; preserve IDs/timestamps omitted by wrappers."""

import math
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from app.providers.tushare import ProviderError

TZ = ZoneInfo("Asia/Shanghai")
SOURCE = "东方财富公开资金流向"
PERIODS = {
    "today": ("1", "f62", "f184", "f3", "f66", "f72", "f78", "f84", "f204", "f205"),
    "5d": ("5", "f164", "f165", "f109", "f166", "f168", "f170", "f172", "f257", "f258"),
    "10d": ("10", "f174", "f175", "f160", "f176", "f178", "f180", "f182", "f260", "f261"),
}


def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def source_time(value):
    n = number(value)
    if not n or n <= 0:
        return None
    try:
        return datetime.fromtimestamp(n, TZ).isoformat()
    except (ValueError, OSError, OverflowError):
        return None


def normalize(row, period, stocks=False):
    _, net, rate, pct, extra, large, medium, small, lead, lead_code = PERIODS[period]
    code = str(row.get("f12", ""))
    if not re.fullmatch(r"\d{6}" if stocks else r"BK\d+", code):
        raise ProviderError("资金来源代码格式异常")
    name = str(row.get("f14") or "").strip()
    if not name:
        raise ProviderError("资金来源名称缺失")
    at = source_time(row.get("f124"))
    result = dict(
        code=code,
        name=name,
        net_amount=number(row.get(net)),
        net_rate=number(row.get(rate)),
        pct_change=number(row.get(pct)),
        extra_large=number(row.get(extra)),
        large=number(row.get(large)),
        medium=number(row.get(medium)),
        small=number(row.get(small)),
        lead_stock=row.get(lead) if row.get(lead) not in (None, "-", "") else None,
        lead_code=row.get(lead_code) if row.get(lead_code) not in (None, "-", "") else None,
        source_as_of=at,
        trade_date=at[:10].replace("-", "") if at else None,
    )
    if stocks:
        # f13 is the source's exchange discriminator, not inferred from the name.
        market = str(row.get("f13"))
        suffix = (
            "SH"
            if market == "1"
            else "BJ"
            if code.startswith(("4", "8", "92"))
            else "SZ"
            if market == "0"
            else None
        )
        result.update(ts_code=f"{code}.{suffix}" if suffix else None, price=number(row.get("f2")))
    return result


class FundFlowProvider:
    def __init__(self, transport=None):
        self.client = httpx.Client(
            timeout=httpx.Timeout(12),
            transport=transport,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"},
        )

    def close(self):
        self.client.close()

    def get(self, host, path, params):
        try:
            response = self.client.get(f"https://{host}.eastmoney.com{path}", params=params)
            response.raise_for_status()
            body = response.json()
            data = body.get("data")
            if not isinstance(data, dict):
                raise ValueError("empty source data")
            return data
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            # Do not expose proxy URLs, transport credentials or full query strings.
            raise ProviderError(
                f"东方财富资金接口获取失败（{type(exc).__name__}），保留已有数据"
            ) from exc

    def listing(self, kind, period, board=None):
        stat, net, *_ = PERIODS[period]
        fields = list(dict.fromkeys(["f12", "f13", "f14", "f2", "f124", *PERIODS[period][1:]]))
        params = dict(
            pn=1,
            pz=100,
            po=1,
            np=1,
            fltt=2,
            invt=2,
            fid=net,
            fid0=net,
            stat=stat,
            fs=f"b:{board}" if board else f"m:90 t:{'2' if kind == 'industry' else '3'}",
            fields=",".join(fields),
        )
        rows, total, seen = [], None, set()
        deadline = time.monotonic() + 90
        for page in range(1, 101):
            if time.monotonic() > deadline:
                raise ProviderError("资金源分页超过总时限，拒绝发布")
            params["pn"] = page
            data = self.get("push2", "/api/qt/clist/get", params)
            count = int(data.get("total", -1))
            if count <= 0 or (total is not None and total != count):
                raise ProviderError("资金源条数异常或分页期间目录变化，拒绝发布")
            total = count
            diff = data.get("diff")
            if isinstance(diff, dict):
                diff = list(diff.values())
            if not isinstance(diff, list) or not diff:
                raise ProviderError("资金源分页截断，拒绝发布")
            for raw in diff:
                row = normalize(raw, period, stocks=bool(board))
                key = row.get("ts_code") if board else row["code"]
                if key is None or key in seen:
                    raise ProviderError("资金源分页代码重复或市场缺失，拒绝发布")
                seen.add(key)
                row["source_rank"] = len(rows) + 1
                rows.append(row)
            if len(rows) >= total:
                break
            time.sleep(0.1)
        if len(rows) != total or not any(r["net_amount"] is not None for r in rows):
            raise ProviderError("资金数据条数不完整或全部资金字段缺失，拒绝发布")
        dates = {r["trade_date"] for r in rows if r["net_amount"] is not None}
        # Timestamp must exist and agree for all effective entries; never guess today's date.
        if len(dates) != 1 or None in dates:
            raise ProviderError("资金源有效记录日期不一致或缺失，拒绝发布")
        day = dates.pop()
        if day > datetime.now(TZ).strftime("%Y%m%d"):
            raise ProviderError("资金源日期位于未来，拒绝发布")
        return dict(
            rows=rows,
            total=total,
            trade_date=day,
            source_as_of=max(r["source_as_of"] for r in rows if r["source_as_of"]),
            period=period,
            source=SOURCE,
        )

    def history(self, code):
        data = self.get(
            "push2his",
            "/api/qt/stock/fflow/daykline/get",
            {
                "lmt": 0,
                "klt": 101,
                "secid": f"90.{code}",
                "fields1": "f1,f2,f3,f7",
                "fields2": ",".join(f"f{i}" for i in range(51, 66)),
            },
        )
        if data.get("code") != code:
            raise ProviderError("资金历史板块身份不一致")
        rows, seen = [], set()
        today = datetime.now(TZ).strftime("%Y%m%d")
        for line in data.get("klines") or []:
            values = line.split(",")
            if len(values) < 11:
                raise ProviderError("资金历史字段截断")
            day = datetime.strptime(values[0], "%Y-%m-%d").strftime("%Y%m%d")
            if day in seen or day > today:
                raise ProviderError("资金历史日期重复或异常")
            seen.add(day)
            # Source does not expose a finalization flag. Keep today's bar as provisional.
            rows.append(
                dict(
                    trade_date=day,
                    net_amount=number(values[1]),
                    net_rate=number(values[6]),
                    small=number(values[2]),
                    medium=number(values[3]),
                    large=number(values[4]),
                    extra_large=number(values[5]),
                    provisional=day == today,
                )
            )
        if not rows:
            raise ProviderError("来源暂无该板块资金历史")
        return dict(
            rows=sorted(rows, key=lambda r: r["trade_date"]),
            source=SOURCE,
            trade_date=max(seen),
            source_as_of=None,
            period="daily",
            total=len(rows),
        )
