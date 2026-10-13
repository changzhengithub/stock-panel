import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select

from app.db import Session
from app.industry import level2_categories
from app.models import (
    Calendar,
    CodeAlias,
    Factor,
    Industry,
    IndustrySnapshot,
    Publication,
    Quote,
    Stock,
    SyncDay,
    utcnow,
)
from app.providers.tushare import PermissionDenied, ProviderError

EXCHANGES = ("SSE", "SZSE", "BSE")


def day_string(value):
    return value.strftime("%Y%m%d")


def cutoff():
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    return day_string(
        now.date() if (now.hour, now.minute) >= (18, 30) else now.date() - timedelta(days=1)
    )


def number(value):
    if value is None:
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def positive_number(value):
    result = number(value)
    return result if result is not None and result > 0 else None


def nonnegative_number(value):
    result = number(value)
    return result if result is not None and result >= 0 else None


def board_for(row):
    if row["exchange"] == "BSE":
        return "北交所"
    if row.get("market") in ("创业板", "科创板"):
        return row["market"]
    if row.get("market") == "主板":
        return "沪市主板" if row["exchange"] == "SSE" else "深市主板"
    return None


class SyncService:
    def __init__(self, provider, sessions=Session, progress=None):
        self.provider = provider
        self.sessions = sessions
        self.progress = progress or (lambda _: None)
        self.warnings = []
        self.st_enabled = True

    def metadata(self, start, end):
        p = self.provider
        self.progress("获取沪深北股票资料与代码映射")
        raw = []
        for exchange in EXCHANGES:
            rows = p.all(
                "stock_basic",
                fields="ts_code,symbol,name,exchange,market,list_date,delist_date,list_status,fullname",
                exchange=exchange,
                list_status="L",
            )
            rows = [row for row in rows if board_for(row)]
            if not rows:
                raise ProviderError(f"{exchange} 股票列表为空，停止更新")
            raw.extend(rows)
        mappings = p.all("bse_mapping")
        old_to_new = {r["o_code"]: r["n_code"] for r in mappings}
        reverse = {r["n_code"]: r["o_code"] for r in mappings}
        # Prefer the current code when a provider returns both sides of a mapping.
        current_codes = {r["ts_code"] for r in raw}
        raw = [r for r in raw if old_to_new.get(r["ts_code"]) not in current_codes]
        self.progress("获取 SW2021 一级行业及成分")
        industries = p.all("index_classify", level="L1", src="SW2021")
        if not industries:
            raise ProviderError("SW2021 一级行业为空")
        categories, by_id = level2_categories()
        if {row["index_code"] for row in industries} != {
            row["parent_id"] for row in categories.values()
        }:
            raise ProviderError("SW2021 二级分类父级与当前一级行业不一致")
        level2 = p.all("index_classify", level="L2", src="SW2021")
        if {row["index_code"] for row in level2} != set(by_id):
            raise ProviderError("SW2021 二级分类版本已变化，保留旧分类并等待核对")
        membership = {}
        level2_membership = {}
        for industry in industries:
            members = p.all("index_member_all", l1_code=industry["index_code"], is_new="Y")
            for member in members:
                code = old_to_new.get(member["ts_code"], member["ts_code"])
                existing = membership.get(code)
                if existing and existing != industry["index_code"]:
                    raise ProviderError(f"{code} 同时属于多个 SW2021 一级行业")
                membership[code] = industry["index_code"]
                l2_code = member.get("l2_code")
                if l2_code:
                    category = by_id.get(l2_code)
                    if not category or category["parent_id"] != industry["index_code"]:
                        raise ProviderError(f"{code} 的 SW2021 二级归属与一级行业冲突")
                    if code in level2_membership and level2_membership[code] != l2_code:
                        raise ProviderError(f"{code} 属于多个 SW2021 二级行业")
                    level2_membership[code] = l2_code
        if not membership:
            raise ProviderError("SW2021 行业成分为空")
        profiles = {}
        for exchange in EXCHANGES:
            try:
                rows = p.all(
                    "stock_company",
                    fields="ts_code,com_name,introduction,main_business",
                    exchange=exchange,
                )
                profiles.update({old_to_new.get(r["ts_code"], r["ts_code"]): r for r in rows})
            except ProviderError as exc:
                self.warnings.append(f"公司资料可选接口：{exc}")
        calendars = {}
        for exchange in ("SSE", "SZSE"):
            rows = p.all("trade_cal", exchange=exchange, start_date=start, end_date=end)
            by_date = {r["cal_date"]: r for r in rows}
            expected = (
                datetime.strptime(end, "%Y%m%d") - datetime.strptime(start, "%Y%m%d")
            ).days + 1
            if len(by_date) != expected:
                raise ProviderError(f"{exchange} 日历不完整：{len(by_date)}/{expected}")
            calendars[exchange] = rows
        with self.sessions.begin() as session:
            session.merge(Industry(id="unclassified", name="未分类", source="未被 SW2021 一级行业覆盖", level=1))
            for row in industries:
                session.merge(Industry(id=row["index_code"], name=row["industry_name"], level=1))
            for category in categories.values():
                session.merge(
                    Industry(
                        id=category["id"], name=category["name"], level=2,
                        parent_id=category["parent_id"], source="Tushare Pro / SW2021",
                    )
                )
            session.flush()
            known = {r.code: r.stock_id for r in session.scalars(select(CodeAlias))}
            seen_ids = set()
            for row in raw:
                code = row["ts_code"]
                identity = (
                    known.get(code)
                    or known.get(reverse.get(code))
                    or known.get(old_to_new.get(code))
                )
                stock = session.get(Stock, identity) if identity else None
                if stock is None:
                    stock = Stock(
                        ts_code=code,
                        symbol=row["symbol"],
                        name=row["name"],
                        exchange=row["exchange"],
                        board=board_for(row),
                        list_date=row["list_date"],
                        industry_id="unclassified",
                    )
                    session.add(stock)
                stock.ts_code, stock.symbol, stock.name = (
                    code,
                    row["symbol"],
                    row["name"],
                )
                stock.exchange, stock.board = row["exchange"], board_for(row)
                stock.list_date, stock.delist_date = (
                    row["list_date"],
                    row.get("delist_date") or None,
                )
                stock.list_status = "L"
                stock.industry_id = membership.get(old_to_new.get(code, code), "unclassified")
                stock.industry_l2_id = level2_membership.get(old_to_new.get(code, code))
                stock.fullname = row.get("fullname") or stock.fullname
                profile = profiles.get(code, {})
                for key, value in [
                    ("fullname", profile.get("com_name")),
                    ("introduction", profile.get("introduction")),
                    ("main_business", profile.get("main_business")),
                ]:
                    if value:
                        setattr(stock, key, value)
                stock.updated_at = utcnow()
                session.flush()
                seen_ids.add(stock.id)
                aliases = {code, reverse.get(code), old_to_new.get(code)} - {None}
                for alias in aliases:
                    if alias in known and known[alias] != stock.id:
                        raise ProviderError(f"{alias} 代码映射冲突，需要人工核对")
                    session.merge(CodeAlias(code=alias, stock_id=stock.id))
                    known[alias] = stock.id
            # Absence in an authoritative current universe is not evidence of a delisting date.
            for stock in session.scalars(select(Stock).where(Stock.list_status == "L")):
                if stock.id not in seen_ids:
                    stock.list_status = "inactive"
            classified = sum(
                old_to_new.get(row["ts_code"], row["ts_code"]) in level2_membership
                for row in raw
            )
            session.merge(
                IndustrySnapshot(
                    id=1, source="Tushare Pro / SW2021", fetched_at=utcnow(),
                    source_updated_at=None, classified_count=classified, stock_count=len(raw),
                )
            )
            for exchange, rows in calendars.items():
                for row in rows:
                    session.merge(
                        Calendar(
                            exchange=exchange,
                            date=row["cal_date"],
                            is_open=bool(int(row["is_open"])),
                            source="Tushare trade_cal",
                        )
                    )
                    if exchange == "SSE":
                        session.merge(
                            Calendar(
                                exchange="BSE",
                                date=row["cal_date"],
                                is_open=bool(int(row["is_open"])),
                                source="Tushare 官方说明：北交所参考上交所日历",
                            )
                        )

    def sync_day(self, date, force=False):
        with self.sessions() as session:
            if not force and session.get(Publication, date):
                return "skipped"
            stocks = list(
                session.scalars(
                    select(Stock).where(Stock.list_status == "L", Stock.list_date <= date)
                )
            )
            open_exchanges = set(
                session.scalars(
                    select(Calendar.exchange).where(
                        Calendar.date == date, Calendar.is_open.is_(True)
                    )
                )
            )
            stocks = [s for s in stocks if s.exchange in open_exchanges]
            aliases = {r.code: r.stock_id for r in session.scalars(select(CodeAlias))}
        if not stocks:
            raise ProviderError(f"{date} 没有可核对的股票或交易日历")
        self.progress(f"{date} 获取行情、指标、复权与交易状态")
        try:

            def mapped(api, **kwargs):
                rows = self.provider.all(api, trade_date=date, **kwargs)
                result = {}
                for row in rows:
                    if row.get("trade_date") != date:
                        raise ProviderError(f"{api} 返回日期不符")
                    sid = aliases.get(row["ts_code"])
                    if sid is not None:
                        # New/old BSE aliases may coexist; conflicting values must be investigated.
                        if sid in result and any(
                            result[sid].get(k) != v for k, v in row.items() if k != "ts_code"
                        ):
                            raise ProviderError(f"{api} 新旧代码数据冲突：{row['ts_code']}")
                        result[sid] = row
                return result

            daily = mapped("daily", fields="ts_code,trade_date,open,high,low,close,pct_chg,vol,amount")
            basic = mapped(
                "daily_basic",
                fields="ts_code,trade_date,total_mv,circ_mv,turnover_rate,pe_ttm,pb,total_share,float_share",
            )
            factors = mapped("adj_factor", fields="ts_code,trade_date,adj_factor")
            suspensions = mapped("suspend_d")
            st, st_source = {}, "unavailable"
            if self.st_enabled:
                try:
                    st = mapped("stock_st")
                    st_source = "stock_st"
                except PermissionDenied:
                    self.st_enabled = False
                    self.warnings.append(
                        "stock_st 无权限；界面仅显示当前名称中的 ST 标记，不推断历史。"
                    )
            quotes, factor_rows, missing = [], [], []
            for stock in stocks:
                sid = stock.id
                d, b, f = daily.get(sid), basic.get(sid), factors.get(sid)
                suspension = suspensions.get(sid, {})
                full_day = suspension.get("suspend_type") == "S" and not suspension.get(
                    "suspend_timing"
                )
                if d:
                    opened, high, low, close, pct, volume, amount = (
                        number(d.get("open")),
                        number(d.get("high")),
                        number(d.get("low")),
                        number(d.get("close")),
                        number(d.get("pct_chg")),
                        number(d.get("vol")),
                        number(d.get("amount")),
                    )
                    cap = number(b.get("total_mv")) if b else None
                    float_cap = positive_number(b.get("circ_mv")) if b else None
                    total_shares = positive_number(b.get("total_share")) if b else None
                    float_shares = positive_number(b.get("float_share")) if b else None
                    if float_cap and cap and float_cap > cap * 1.02:
                        float_cap = None
                    if float_shares and total_shares and float_shares > total_shares * 1.02:
                        float_shares = None
                    pe_ratio = positive_number(b.get("pe_ttm")) if b else None
                    factor = number(f.get("adj_factor")) if f else None
                    if (
                        opened is None
                        or opened <= 0
                        or high is None
                        or high <= 0
                        or low is None
                        or low <= 0
                        or close is None
                        or close <= 0
                        or low > min(opened, close)
                        or high < max(opened, close)
                        or pct is None
                        or volume is None
                        or volume < 0
                        or amount is None
                        or amount < 0
                        or cap is None
                        or cap <= 0
                        or factor is None
                        or factor <= 0
                    ):
                        missing.append(stock.ts_code)
                        continue
                    quotes.append(
                        Quote(
                            stock_id=sid,
                            trade_date=date,
                            open=opened,
                            high=high,
                            low=low,
                            close=close,
                            volume=volume,
                            pct_chg=pct,
                            amount=amount * 1000,
                            market_cap=cap * 10000,
                            float_market_cap=float_cap * 10000 if float_cap else None,
                            turnover_rate=nonnegative_number(b.get("turnover_rate")) if b else None,
                            pe_ratio=pe_ratio,
                            pe_basis="TTM" if pe_ratio is not None else None,
                            pb_ratio=positive_number(b.get("pb")) if b else None,
                            total_shares=total_shares * 10000 if total_shares else None,
                            float_shares=float_shares * 10000 if float_shares else None,
                            status="trading",
                            is_st=sid in st if st_source == "stock_st" else None,
                            st_source=st_source,
                        )
                    )
                    factor_rows.append(Factor(stock_id=sid, trade_date=date, value=factor))
                elif full_day:
                    quotes.append(
                        Quote(
                            stock_id=sid,
                            trade_date=date,
                            status="suspended",
                            is_st=sid in st if st_source == "stock_st" else None,
                            st_source=st_source,
                        )
                    )
                    if f and number(f.get("adj_factor")) and number(f["adj_factor"]) > 0:
                        factor_rows.append(
                            Factor(
                                stock_id=sid,
                                trade_date=date,
                                value=number(f["adj_factor"]),
                            )
                        )
                else:
                    missing.append(stock.ts_code)
            if missing:
                raise ProviderError(
                    f"{date} {len(missing)} 只股票必需行情缺失：" + ", ".join(missing[:25])
                )
            if not daily or not quotes:
                raise ProviderError(f"{date} 行情为空")
            with self.sessions.begin() as session:
                session.execute(delete(Quote).where(Quote.trade_date == date))
                session.execute(delete(Factor).where(Factor.trade_date == date))
                session.add_all(quotes + factor_rows)
                session.merge(
                    Publication(trade_date=date, stock_count=len(quotes), published_at=utcnow())
                )
                session.merge(
                    SyncDay(
                        trade_date=date,
                        state="complete",
                        error=None,
                        updated_at=utcnow(),
                    )
                )
            return "published"
        except Exception as exc:
            with self.sessions.begin() as session:
                session.merge(
                    SyncDay(
                        trade_date=date,
                        state="failed",
                        error=str(exc),
                        updated_at=utcnow(),
                    )
                )
            raise

    def run(self, start, end, force=False):
        self.metadata(start, end)
        with self.sessions() as session:
            dates = sorted(
                set(
                    session.scalars(
                        select(Calendar.date).where(
                            Calendar.date >= start,
                            Calendar.date <= end,
                            Calendar.is_open.is_(True),
                        )
                    )
                ),
                reverse=True,
            )
        failures, complete = [], 0
        for date in dates:
            try:
                self.sync_day(date, force)
                complete += 1
            except PermissionDenied:
                raise
            except ProviderError as exc:
                failures.append(str(exc))
            self.progress(
                f"已处理 {complete + len(failures)}/{len(dates)} 个交易日；失败 {len(failures)}"
            )
        return {
            "days": len(dates),
            "complete": complete,
            "failures": failures,
            "warnings": self.warnings,
        }
