"""Resumable paginated public data acquisition; no automatic chain review/publication."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select

from app.business_models import BusinessCollection, BusinessSnapshot
from app.chain_service import digest
from app.models import Stock, utcnow
from app.settings import ROOT
from app.universe import visible_stock

URL = "https://datacenter.eastmoney.com/securities/api/data/v1/get"
PROFILE_COLUMNS = (
    "SECUCODE,SECURITY_NAME_ABBR,ORG_NAME,ORG_PROFIE,MAIN_BUSINESS,ORG_WEB,SECURITY_TYPE,MAX_DATE"
)
FINANCIAL_COLUMNS = "SECUCODE,SECURITY_NAME_ABBR,REPORT_DATE,REPORT_NAME,MAINOP_TYPE,ITEM_NAME,MAIN_BUSINESS_INCOME,MBI_RATIO,MAIN_BUSINESS_COST,MAIN_BUSINESS_RPOFIT,GROSS_RPOFIT_RATIO,TOTAL_BUSINESS_INCOME,IS_NEW,RANK"


def current_periods(today=None):
    today = today or date.today()
    # Use periods whose standard disclosure deadline has passed; record actual missing data.
    year = today.year if today.month >= 9 else today.year - 1
    annual = today.year - 1 if today.month >= 5 else today.year - 2
    return [f"{annual}-12-31", f"{year}-06-30"]


def collection_periods(today=None):
    """Include newly ended periods as well as mature periods, without assuming disclosure."""
    today = today or datetime.now(ZoneInfo("Asia/Shanghai")).date()
    periods = current_periods(today)
    periods.append(f"{today.year - 1}-12-31")
    if today.month >= 7:
        periods.append(f"{today.year}-06-30")
    return sorted(set(periods))


class BusinessCollector:
    def __init__(self, cache, *, direct=False, refresh=False, stop=None):
        self.cache = Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.direct, self.refresh = direct, refresh
        self.stop = stop

    def page(self, report, filters, page, columns):
        params = dict(
            reportName=report,
            columns=columns,
            pageSize=500,
            pageNumber=page,
            filter=filters,
            sortColumns="SECUCODE" if "ORG" in report else "SECUCODE,REPORT_DATE,MAINOP_TYPE,RANK",
            sortTypes="1" if "ORG" in report else "1,-1,1,1",
            source="HSF10",
            client="PC",
        )
        path = self.cache / (digest(params) + ".json")
        if path.exists() and not self.refresh:
            envelope = json.loads(path.read_text())
            if digest(envelope["response"]) != envelope["sha256"]:
                raise ValueError(f"缓存校验失败：{path.name}")
            return envelope
        error = None
        for attempt in range(3):
            if self.stop and self.stop.is_set():
                raise ValueError("服务停止，取消本轮产业分析更新")
            try:
                with httpx.Client(timeout=40, trust_env=not self.direct) as client:
                    response = client.get(URL, params=params)
                    response.raise_for_status()
                    value = response.json()
                if not value.get("success") or not value.get("result"):
                    if value.get("code") == 9201 or value.get("message") == "返回数据为空":
                        value = {
                            **value,
                            "success": True,
                            "result": {"data": [], "count": 0, "pages": 1},
                        }
                    else:
                        raise ValueError(value.get("message", "数据源没有有效结果"))
                envelope = dict(
                    url=str(response.url),
                    collected_at=utcnow(),
                    sha256=digest(value),
                    response=value,
                )
                temp = path.with_suffix(".tmp")
                temp.write_text(json.dumps(envelope, ensure_ascii=False))
                temp.replace(path)
                return envelope
            except (httpx.HTTPError, ValueError) as exc:
                error = exc
                time.sleep(0.4 * 2**attempt)
        raise ValueError(f"{report} 第 {page} 页采集失败：{type(error).__name__}: {error}")

    def all(self, report, filters, columns, progress=print):
        first = self.page(report, filters, 1, columns)
        result = first["response"]["result"]
        count, pages = result["count"], result["pages"]
        envelopes = [first]
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {
                n: pool.submit(self.page, report, filters, n, columns) for n in range(2, pages + 1)
            }
            for n, future in futures.items():
                envelope = future.result()
                other = envelope["response"]["result"]
                if (other["count"], other["pages"]) != (count, pages):
                    raise ValueError("采集期间源分页数量变化，请刷新本批缓存重新采集")
                envelopes.append(envelope)
                if n % 20 == 0 or n == pages:
                    progress(
                        json.dumps(dict(report=report, page=n, pages=pages), ensure_ascii=False),
                        flush=True,
                    )
        rows = [r for e in envelopes for r in e["response"]["result"]["data"]]
        if len(rows) != count:
            raise ValueError("数据源页数与实际记录数不一致，不发布不完整数据")
        return rows, envelopes


def snapshots(session):
    result = {}
    for x in session.scalars(
        select(BusinessSnapshot).order_by(
            BusinessSnapshot.collected_at, BusinessSnapshot.content_hash
        )
    ):
        result[x.ts_code] = x
    # A company can revert to previously seen content. The latest successful acquisition
    # explicitly selects its immutable snapshots rather than relying only on creation time.
    run = session.scalar(
        select(BusinessCollection)
        .where(BusinessCollection.state == "complete")
        .order_by(BusinessCollection.started_at.desc(), BusinessCollection.id.desc())
        .limit(1)
    )
    if run and run.payload.get("snapshot_hashes"):
        selected = run.payload["snapshot_hashes"]
        for x in session.scalars(select(BusinessSnapshot)):
            if selected.get(x.ts_code) == x.content_hash:
                result[x.ts_code] = x
    return result


def collect(factory, *, direct=False, refresh=False, cache=None, strict=False, stop=None):
    from app.jobs.industry_chains import chain_lock

    with chain_lock():
        return _collect(
            factory, direct=direct, refresh=refresh, cache=cache, strict=strict, stop=stop
        )


def _collect(factory, *, direct=False, refresh=False, cache=None, strict=False, stop=None):
    run_id = uuid4().hex
    periods = collection_periods()
    with factory() as s:
        codes = set(s.scalars(select(Stock.ts_code).where(visible_stock(s))))
    with factory.begin() as s:
        s.add(
            BusinessCollection(
                id=run_id, state="running", payload=dict(universe=len(codes), periods=periods)
            )
        )
    try:
        collector = BusinessCollector(
            cache or ROOT / "data/business-cache" / date.today().isoformat(),
            direct=direct,
            refresh=refresh,
            stop=stop,
        )
        profiles, profile_pages = collector.all(
            "RPT_F10_ORG_BASICINFO", '(SECURITY_TYPE="A股")', PROFILE_COLUMNS
        )
        profile_map = {}
        for p in profiles:
            code = p["SECUCODE"]
            if code in codes:
                if code in profile_map and profile_map[code] != p:
                    raise ValueError(f"公司资料重复且不一致：{code}")
                profile_map[code] = p
        for code in sorted(codes - profile_map.keys()):
            rows, pages = collector.all(
                "RPT_F10_ORG_BASICINFO", f'(SECUCODE="{code}")', PROFILE_COLUMNS
            )
            profile_pages.extend(pages)
            for row in rows:
                if row["SECUCODE"] == code:
                    profile_map[code] = row
        finance, finance_pages = collector.all(
            "RPT_F10_FN_MAINOP",
            "(REPORT_DATE in ('" + "','".join(periods) + "'))",
            FINANCIAL_COLUMNS,
        )
        financial_map = {}
        seen = set()
        for f in finance:
            code = f["SECUCODE"]
            if code not in codes:
                continue
            identity = (code, f["REPORT_DATE"], str(f["MAINOP_TYPE"]), f["ITEM_NAME"])
            if identity in seen:
                # Identical duplicate source rows are harmless; conflicting values fail validation.
                previous = next(
                    x
                    for x in financial_map[code]
                    if (code, x["REPORT_DATE"], str(x["MAINOP_TYPE"]), x["ITEM_NAME"]) == identity
                )
                if digest(previous) != digest(f):
                    raise ValueError(f"财务分部重复且不一致：{identity}")
                continue
            seen.add(identity)
            financial_map.setdefault(code, []).append(f)
        fallback = {}
        for code in sorted(codes - financial_map.keys()):
            envelope = collector.page(
                "RPT_F10_FN_MAINOP", f'(SECUCODE="{code}")', 1, FINANCIAL_COLUMNS
            )
            finance_pages.append(envelope)
            fallback[code] = sorted(
                {f["REPORT_DATE"][:10] for f in envelope["response"]["result"]["data"]},
                reverse=True,
            )
        collected_at = max(e["collected_at"] for e in profile_pages + finance_pages)
        report = dict(
            run_id=run_id,
            universe=len(codes),
            profile_count=len(profile_map),
            business_count=sum(bool(p.get("MAIN_BUSINESS")) for p in profile_map.values()),
            financial_count=len(financial_map),
            financial_rows=sum(map(len, financial_map.values())),
            missing_profiles=sorted(codes - profile_map.keys()),
            missing_financials=sorted(codes - financial_map.keys()),
            periods=periods,
            available_other_periods=fallback,
            source="东方财富 F10 汇总，未逐份核验原始公告",
            collected_at=collected_at,
            pages=len(profile_pages) + len(finance_pages),
        )
        if strict:
            validate_collection(report, factory)
        report["snapshot_hashes"] = {}
        with factory.begin() as s:
            previous = snapshots(s)
            for code in sorted(codes):
                p = profile_map.get(code)
                payload = dict(
                    profile=p,
                    financials=financial_map.get(code, []),
                    periods=periods,
                    available_other_periods=fallback.get(code, []),
                    profile_status="collected"
                    if p and p.get("MAIN_BUSINESS")
                    else "source_missing",
                    financial_status="collected" if code in financial_map else "source_missing",
                    source="eastmoney-f10",
                    source_url="https://data.eastmoney.com/stockdata/" + code[:6] + ".html",
                    collected_at=collected_at,
                    review_status="vendor_snapshot",
                )
                semantic = {k: v for k, v in payload.items() if k != "collected_at"}
                old = previous.get(code)
                old_semantic = (
                    {k: v for k, v in old.payload.items() if k != "collected_at"} if old else None
                )
                content_hash = old.content_hash if old_semantic == semantic else digest(semantic)
                report["snapshot_hashes"][code] = content_hash
                if not s.get(BusinessSnapshot, (code, content_hash)):
                    s.add(
                        BusinessSnapshot(
                            ts_code=code,
                            content_hash=content_hash,
                            payload=payload,
                            collected_at=collected_at,
                        )
                    )
                stock = s.scalar(select(Stock).where(Stock.ts_code == code))
                if p and stock:
                    if not stock.main_business:
                        stock.main_business = p.get("MAIN_BUSINESS")
                    if not stock.introduction:
                        stock.introduction = p.get("ORG_PROFIE")
            run = s.get(BusinessCollection, run_id)
            run.state = "complete"
            run.finished_at = utcnow()
            run.payload = report
        return report
    except Exception as exc:
        with factory.begin() as s:
            run = s.get(BusinessCollection, run_id)
            run.state = "failed"
            run.finished_at = utcnow()
            run.payload = {**run.payload, "error": str(exc)[:1200]}
        raise


def validate_collection(report, factory):
    """Reject a degraded provider batch before it replaces the successful snapshot selection."""
    total = report["universe"]
    if (
        not total
        or report["profile_count"] / total < 0.95
        or report["business_count"] / total < 0.95
    ):
        raise ValueError("公司主营资料覆盖不足 95%，保留上一批可用数据")
    if report["financial_count"] / total < 0.90:
        raise ValueError("分部财务覆盖不足 90%，保留上一批可用数据")
    with factory() as s:
        old = s.scalar(
            select(BusinessCollection)
            .where(BusinessCollection.state == "complete")
            .order_by(BusinessCollection.started_at.desc())
            .limit(1)
        )
        if old and set(old.payload.get("periods", [])) <= set(report["periods"]):
            for field in ("business_count", "financial_count"):
                prior = old.payload.get(field, 0) / max(old.payload.get("universe", 1), 1)
                if report[field] / total < prior * 0.95:
                    raise ValueError("相同报告期资料覆盖明显下降，保留上一批可用数据")
