"""Free-source snapshots and per-stock history have separate completeness states."""

import json
from datetime import datetime, timedelta

from sqlalchemy import delete, or_, select

from app.db import Session
from app.industry import level2_categories, official_assignments
from app.models import (
    Calendar,
    CodeAlias,
    HistoryBar,
    HistoryImport,
    Industry,
    IndustrySnapshot,
    Publication,
    Quote,
    Representative,
    Stock,
    utcnow,
)
from app.providers.free import FreeProvider
from app.providers.tushare import ProviderError


class FreeSyncService:
    def __init__(self, provider, sessions=Session, progress=None):
        self.provider, self.sessions = provider, sessions
        self.progress = progress or (lambda _: None)
        self.warnings = []

    def metadata(self, start, end):
        self.progress("获取沪深北交易所股票名单")
        stocks = self.provider.universe()
        self.progress("获取 SW2021 一级行业与全部成分")
        industries, membership = self.provider.industries(), {}
        for index, industry in enumerate(industries):
            self.progress(f"SW2021 行业 {index + 1}/{len(industries)}：{industry['name']}")
            for code in self.provider.members(industry["id"]):
                if code in membership and membership[code] != industry["id"]:
                    raise ProviderError(f"{code} 属于多个 SW2021 一级行业，停止元数据更新")
                membership[code] = industry["id"]
        categories, _ = level2_categories()
        if {row["parent_id"] for row in categories.values()} != {row["id"] for row in industries}:
            raise ProviderError("SW2021 二级分类父级与当前一级行业不一致")
        self.progress("获取 SW2021 官方网站个股分类历史并核验二级归属")
        assignments, source_updated_at, classified = official_assignments(
            self.provider.classification_history(), stocks, membership
        )
        if classified < len(stocks):
            self.warnings.append(
                f"{len(stocks) - classified} 只股票暂无 SW2021 官方二级归属，已标记未细分。"
            )
        opens = self.provider.calendar()
        if not opens or max(opens) < end:
            raise ProviderError("免费交易日历未覆盖目标日期，拒绝推测休市日")
        with self.sessions.begin() as s:
            existing = {r.ts_code: r for r in s.scalars(select(Stock))}
            incoming = {r["ts_code"] for r in stocks}
            aliases = {r.code: r.stock_id for r in s.scalars(select(CodeAlias))}
            # A new BSE code cannot be merged by name alone. Reuse verified aliases only.
            absent_bse = {
                r.name
                for r in existing.values()
                if r.exchange == "BSE" and r.ts_code not in incoming
            }
            for row in stocks:
                if (
                    row["exchange"] == "BSE"
                    and row["ts_code"] not in aliases
                    and row["name"] in absent_bse
                ):
                    raise ProviderError(
                        f"北交所 {row['name']} 疑似代码变更；请先导入经核实的代码映射"
                    )
            s.merge(Industry(id="unclassified", name="未分类", source="SW2021 未覆盖", level=1))
            for row in industries:
                s.merge(Industry(**row, source="AKShare / SW2021 官方网站", level=1))
            for category in categories.values():
                s.merge(
                    Industry(
                        id=category["id"],
                        name=category["name"],
                        parent_id=category["parent_id"],
                        level=2,
                        source="SW2021 行业分类标准 / 官网个股归属",
                    )
                )
            s.flush()
            seen = set()
            for row in stocks:
                code = row["ts_code"]
                stock = s.get(Stock, aliases[code]) if code in aliases else existing.get(code)
                if stock is None:
                    stock = Stock(**row, industry_id="unclassified")
                    s.add(stock)
                else:
                    for key, value in row.items():
                        if value is not None:
                            setattr(stock, key, value)
                category = assignments[code]
                stock.industry_id = (
                    category["parent_id"] if category else membership.get(code, "unclassified")
                )
                stock.industry_l2_id = category["id"] if category else None
                stock.list_status, stock.updated_at = "L", utcnow()
                s.flush()
                s.merge(CodeAlias(code=code, stock_id=stock.id))
                seen.add(stock.id)
            for stock in existing.values():
                if stock.id not in seen:
                    stock.list_status = "inactive"
            s.merge(
                IndustrySnapshot(
                    id=1,
                    source="SW2021 官方网站的个股分类文件",
                    fetched_at=utcnow(),
                    source_updated_at=source_updated_at,
                    classified_count=classified,
                    stock_count=len(stocks),
                )
            )
            date = datetime.strptime(start, "%Y%m%d")
            open_set = set(opens)
            while date.strftime("%Y%m%d") <= end:
                value = date.strftime("%Y%m%d")
                for exchange in ("SSE", "SZSE", "BSE"):
                    s.merge(
                        Calendar(
                            exchange=exchange,
                            date=value,
                            is_open=value in open_set,
                            source="AKShare / 新浪交易日历；沪深北共同休市口径",
                        )
                    )
                date += timedelta(days=1)
        return [d for d in opens if start <= d <= end]

    def snapshot(self, end, force=False):
        with self.sessions() as s:
            dates = list(
                s.scalars(
                    select(Calendar.date).where(
                        Calendar.exchange == "SSE", Calendar.is_open.is_(True), Calendar.date <= end
                    )
                )
            )
            if not dates:
                raise ProviderError("目标区间没有交易日历")
            date = max(dates)
            existing = s.get(Publication, date)
            if (
                existing
                and existing.source.startswith("免费公开数据")
                and not force
                and not existing.missing_count
            ):
                return date
            stocks = list(
                s.scalars(select(Stock).where(Stock.list_status == "L", Stock.list_date <= date))
            )
        self.progress(f"获取 {date} 全市场行情快照，校验分页和源日期")
        rows = {r["ts_code"]: r for r in self.provider.snapshot()}
        self.warnings.extend(getattr(self.provider, "warnings", []))
        quotes, missing, missing_cap = [], [], 0
        for stock in stocks:
            row = rows.get(stock.ts_code)
            # Zero turnover does not prove a suspension. Only dated, actively traded rows rank.
            valid = (
                row
                and row["date"] == date
                and row["time"] >= "150000"
                and row["close"] is not None
                and row["close"] > 0
                and row["pct_chg"] is not None
                and row["amount"] is not None
                and row["amount"] > 0
            )
            if not valid:
                missing.append(stock.ts_code)
                quotes.append(Quote(stock_id=stock.id, trade_date=date, status="unavailable"))
                continue
            cap = (
                row["market_cap"]
                if row["market_cap"] is not None and row["market_cap"] > 0
                else None
            )
            missing_cap += cap is None
            quotes.append(
                Quote(
                    stock_id=stock.id,
                    trade_date=date,
                    close=row["close"],
                    pct_chg=row["pct_chg"],
                    amount=row["amount"],
                    market_cap=cap,
                    float_market_cap=row.get("float_market_cap"),
                    turnover_rate=row.get("turnover_rate"),
                    pe_ratio=row.get("pe_ratio"),
                    pe_basis=row.get("pe_basis") if row.get("pe_ratio") is not None else None,
                    pb_ratio=row.get("pb_ratio"),
                    total_shares=row.get("total_shares"),
                    float_shares=row.get("float_shares"),
                    status="trading",
                    st_source="current_name",
                )
            )
        if not stocks or len(missing) / len(stocks) > 0.05:
            raise ProviderError(
                f"{date} 有效行情不足 95%（{len(stocks) - len(missing)}/{len(stocks)}）；可能是日期不符或上游异常，保留旧快照"
            )
        with self.sessions.begin() as s:
            s.execute(delete(Quote).where(Quote.trade_date == date))
            s.add_all(quotes)
            s.merge(
                Publication(
                    trade_date=date,
                    stock_count=len(stocks),
                    source=self.provider.snapshot_source,
                    missing_count=len(missing),
                    missing_cap_count=missing_cap,
                    published_at=utcnow(),
                )
            )
        if missing:
            self.warnings.append(
                f"行情快照 {len(stocks) - len(missing)}/{len(stocks)}；{len(missing)} 只缺失/日期不符/无成交，未推断停牌，不参与涨跌榜。"
                + "、".join(missing[:25])
            )
        if missing_cap:
            self.warnings.append(f"{missing_cap} 只股票缺少市值，已显示为空")
        return date

    def history_one(self, stock, start, end, force=False):
        import fcntl
        from pathlib import Path

        database_path = Path(self.sessions.kw["bind"].url.database)
        path = database_path.with_suffix(f".history-{stock.id}.lock")
        with path.open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return "busy"
            return self._history_one(stock, start, end, force)

    def _history_one(self, stock, start, end, force=False):
        start = max(start, stock.list_date)
        if start > end:
            return "skipped"
        with self.sessions() as s:
            old = s.get(HistoryImport, stock.id)
            if old and old.state in ("complete", "partial"):
                start = min(start, old.start_date)
            cached_bar = s.scalar(
                select(HistoryBar.trade_date).where(HistoryBar.stock_id == stock.id).limit(1)
            )
            close_only_bar = s.scalar(
                select(HistoryBar.trade_date)
                .where(
                    HistoryBar.stock_id == stock.id,
                    or_(
                        HistoryBar.adjusted_open.is_(None),
                        HistoryBar.adjusted_high.is_(None),
                        HistoryBar.adjusted_low.is_(None),
                        HistoryBar.volume.is_(None),
                        HistoryBar.raw_open.is_(None),
                    ),
                )
                .limit(1)
            )
            if (
                not force
                and old
                and old.state in ("complete", "partial")
                and old.basis_date == end
                and old.start_date <= start
                and cached_bar
                and not close_only_bar
            ):
                return "skipped"
            quote = s.get(Quote, (stock.id, end))
            dates = set(
                s.scalars(
                    select(Calendar.date).where(
                        Calendar.exchange == stock.exchange,
                        Calendar.is_open.is_(True),
                        Calendar.date >= start,
                        Calendar.date <= end,
                    )
                )
            )
        try:
            if hasattr(self.provider, "history_pair"):
                raw_rows, adjusted_rows = self.provider.history_pair(stock.symbol, start, end)
            else:
                raw_rows = self.provider.history(stock.symbol, start, end)
                adjusted_rows = self.provider.history(stock.symbol, start, end, adjusted=True)
            adjusted = {r["date"]: r for r in adjusted_rows}
            raw = {r["date"]: r for r in raw_rows}
            if end not in raw or end not in adjusted:
                raise ProviderError("历史末日缺失，无法确认统一复权基准；未推断停牌")
            if len(raw) != len(raw_rows) or len(adjusted) != len(adjusted_rows):
                raise ProviderError("历史 K 线日期重复")
            if any(row.get("volume") is None or row["volume"] < 0 for row in raw_rows):
                raise ProviderError("原始历史日线缺少有效成交量")
            if set(raw) != set(adjusted) or set(raw) - dates:
                raise ProviderError("原始/复权日线或交易日历日期不一致")
            if quote and quote.close is not None and abs(raw[end]["close"] - quote.close) > 0.011:
                raise ProviderError("历史末日价格与行情快照不符，暂不覆盖历史")
            missing = sorted(dates - set(raw))
            anchor = adjusted[end]["close"]
            if anchor <= 0:
                raise ProviderError("复权 K 线基准收盘价无效")
            scale = raw[end]["close"] / anchor
            bars = [
                HistoryBar(
                    stock_id=stock.id,
                    trade_date=date,
                    raw_close=raw_row["close"],
                    raw_open=raw_row["open"],
                    raw_high=raw_row["high"],
                    raw_low=raw_row["low"],
                    adjusted_open=round(adjusted[date]["open"] * scale, 4),
                    adjusted_high=round(adjusted[date]["high"] * scale, 4),
                    adjusted_low=round(adjusted[date]["low"] * scale, 4),
                    adjusted_close=round(adjusted[date]["close"] * scale, 4),
                    volume=raw_row.get("volume"),
                )
                for date, raw_row in raw.items()
            ]
            if any(
                bar.adjusted_low > min(bar.adjusted_open, bar.adjusted_close)
                or bar.adjusted_high < max(bar.adjusted_open, bar.adjusted_close)
                for bar in bars
            ):
                raise ProviderError("复权 K 线开高低收价格关系异常")
            with self.sessions.begin() as s:
                s.execute(delete(HistoryBar).where(HistoryBar.stock_id == stock.id))
                s.add_all(bars)
                s.merge(
                    HistoryImport(
                        stock_id=stock.id,
                        start_date=start,
                        basis_date=end,
                        source=f"{getattr(self.provider, 'history_channel', '免费源')}后复权日 K 线 / 基准日原始收盘价归一化",
                        state="partial" if missing else "complete",
                        missing_days=json.dumps(missing),
                        error=None,
                        updated_at=utcnow(),
                    )
                )
            return "partial" if missing else "complete"
        except Exception as exc:
            with self.sessions.begin() as s:
                old = s.get(HistoryImport, stock.id)
                if old:
                    # Keep last usable series/anchor intact while recording the failed refresh.
                    old.error = str(exc)
                    old.updated_at = utcnow()
                else:
                    s.add(
                        HistoryImport(
                            stock_id=stock.id,
                            start_date=start,
                            basis_date=end,
                            source="东方财富",
                            state="failed",
                            error=str(exc),
                            missing_days="[]",
                        )
                    )
            raise

    def backfill(self, start, end, force=False, limit=None, codes=None):
        with self.sessions() as s:
            query = (
                select(Stock)
                .outerjoin(Representative, Representative.stock_id == Stock.id)
                .where(Stock.list_status == "L", Stock.list_date <= end)
                .order_by(Representative.stock_id.is_(None), Stock.symbol)
            )
            if codes:
                query = query.where(Stock.ts_code.in_(codes))
            stocks = list(s.scalars(query))
            if codes and len(stocks) != len(set(codes)):
                raise ProviderError("--codes 包含不存在的当前股票代码，请使用 600519.SH 等格式")
            imported = {h.stock_id: h for h in s.scalars(select(HistoryImport))}
            missing_volume = set(
                s.scalars(select(HistoryBar.stock_id).where(HistoryBar.volume.is_(None)).distinct())
            )
            done = {
                stock.id
                for stock in stocks
                if (h := imported.get(stock.id))
                and h.basis_date == end
                and h.start_date <= max(start, stock.list_date)
                and h.state in ("complete", "partial")
                and stock.id not in missing_volume
            }
        pending = [stock for stock in stocks if force or stock.id not in done]
        if limit is not None:
            pending = pending[:limit]
        failures, complete = [], 0
        for i, stock in enumerate(pending):
            self.progress(f"历史回填 {i + 1}/{len(pending)}：{stock.name} {stock.symbol}")
            try:
                if self.history_one(stock, start, end, force) != "busy":
                    complete += 1
            except Exception as exc:
                failures.append(f"{stock.ts_code}: {exc}")
        return {
            "days": 0,
            "complete": complete,
            "failures": failures,
            "warnings": self.warnings,
            "history_requested": len(pending),
            "history_pending": max(0, len(stocks) - len(done) - complete),
        }

    def run(self, start, end, force=False, command="sync", limit=None, codes=None):
        if command != "backfill":
            dates = self.metadata(start, end)
            end = self.snapshot(end, force)
            self.progress(f"行情快照已保存：{end}；开始独立历史回填")
        else:
            with self.sessions() as s:
                publication = s.scalar(
                    select(Publication)
                    .where(
                        Publication.source.startswith("免费公开数据"), Publication.trade_date <= end
                    )
                    .order_by(Publication.trade_date.desc())
                )
                if not publication:
                    raise ProviderError("请先运行 bootstrap 同步免费行情快照")
                end = publication.trade_date
            opens = self.provider.calendar()
            if not opens or max(opens) < end:
                raise ProviderError("免费交易日历未覆盖目标日期，拒绝推测休市日")
            dates = [day for day in opens if start <= day <= end]
            with self.sessions.begin() as s:
                for exchange in ("SSE", "SZSE", "BSE"):
                    for day in dates:
                        s.merge(
                            Calendar(
                                exchange=exchange, date=day, is_open=True, source="公开交易日历"
                            )
                        )
        result = self.backfill(start, end, force, limit, codes)
        self.warnings = list(dict.fromkeys(self.warnings + getattr(self.provider, "warnings", [])))
        if result["history_pending"]:
            self.warnings.append(
                f"尚有 {result['history_pending']} 只股票未完成本次历史处理；可运行 backfill 或在详情页按需补取。"
            )
        result["warnings"] = self.warnings
        result["snapshot_date"], result["calendar_days"] = end, len(dates)
        return result


def warm_history(stock_id, requested_start=None):
    """Read-through history cache; history_one shares its lock with CLI imports."""
    provider = FreeProvider()
    start = end = None
    try:
        with Session() as s:
            stock = s.get(Stock, stock_id)
            publication = s.scalar(select(Publication).order_by(Publication.trade_date.desc()))
            if not stock or not publication or not publication.source.startswith("免费公开数据"):
                return
            end = publication.trade_date
        start = (datetime.strptime(end, "%Y%m%d") - timedelta(days=366)).strftime("%Y%m%d")
        start = max(stock.list_date, requested_start or start)
        with Session() as s:
            old = s.get(HistoryImport, stock_id)
            if old and old.state in ("complete", "partial"):
                start = min(start, old.start_date)
        opens = provider.calendar()
        if not opens or max(opens) < end:
            raise ValueError("交易日历未覆盖目标日期")
        with Session.begin() as s:
            for day in opens:
                if start <= day <= end:
                    s.merge(
                        Calendar(
                            exchange=stock.exchange, date=day, is_open=True, source="公开交易日历"
                        )
                    )
        FreeSyncService(provider).history_one(stock, start, end)
    except Exception as exc:
        # Calendar failures happen before history_one; expose them without discarding cached bars.
        if start and end:
            with Session.begin() as s:
                old = s.get(HistoryImport, stock_id)
                if old:
                    old.error = str(exc)
                    old.updated_at = utcnow()
                else:
                    s.add(
                        HistoryImport(
                            stock_id=stock_id,
                            start_date=start,
                            basis_date=end,
                            source="免费公开数据",
                            state="failed",
                            error=str(exc),
                            missing_days="[]",
                        )
                    )
    finally:
        provider.close()


def warm_profile(stock_id):
    """Optional company text; failures never hold up quotes or charts."""
    import fcntl
    import time

    from app.settings import db_path

    path = db_path().parent / f"profile-{stock_id}.lock"
    with path.open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        # Bound failed requests when several tabs visit the same profile.
        lock.seek(0)
        previous = lock.read().strip()
        if previous and time.time() - float(previous) < 300:
            return
        lock.seek(0)
        lock.truncate()
        lock.write(str(time.time()))
        lock.flush()
        provider = FreeProvider()
        try:
            with Session() as s:
                stock = s.get(Stock, stock_id)
                if not stock or (stock.introduction and stock.main_business):
                    return
                symbol = stock.symbol
            values = provider.profile(symbol)
            with Session.begin() as s:
                stock = s.get(Stock, stock_id)
                for key, value in values.items():
                    if value:
                        setattr(stock, key, value)
                stock.updated_at = utcnow()
        except ProviderError:
            pass
        finally:
            provider.close()
