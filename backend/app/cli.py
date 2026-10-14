import argparse
import fcntl
import json
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from app.db import Session, migrate
from app.jobs.concepts import sync_concepts
from app.jobs.concepts_tdx import sync_tdx_concepts
from app.jobs.free_sync import FreeSyncService
from app.jobs.leaders import refresh_index_leaders
from app.jobs.sync import SyncService, cutoff
from app.models import SyncRun, utcnow
from app.providers.free import FreeProvider, free_cutoff
from app.providers.tushare import ProviderError, Tushare
from app.settings import data_provider, db_path, token


@contextmanager
def sync_lock():
    path = db_path().with_suffix(".sync.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ProviderError("已有同步任务运行，请稍后再试") from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def report(value):
    print(json.dumps(value, ensure_ascii=False, indent=2), flush=True)


def valid_date(value):
    try:
        datetime.strptime(value, "%Y%m%d")
    except ValueError:
        raise argparse.ArgumentTypeError("日期使用 YYYYMMDD") from None
    return value


def doctor(provider):
    date = cutoff()
    recent = (datetime.strptime(date, "%Y%m%d") - timedelta(days=30)).strftime("%Y%m%d")
    calendar = provider.all(
        "trade_cal", exchange="SSE", start_date=recent, end_date=date, is_open="1"
    )
    if not calendar:
        raise ProviderError("交易日历为空")
    date = max(r["cal_date"] for r in calendar)
    results = {"trade_date": date, "checks": {}}
    for exchange in ("SSE", "SZSE", "BSE"):
        rows = provider.all("stock_basic", exchange=exchange, list_status="L")
        if not rows:
            raise ProviderError(f"{exchange} 股票列表为空")
        results["checks"][exchange] = len(rows)
    for api, params in [
        ("daily", {"trade_date": date}),
        ("daily_basic", {"trade_date": date}),
        ("adj_factor", {"trade_date": date}),
        ("suspend_d", {"trade_date": date}),
        ("index_classify", {"level": "L1", "src": "SW2021"}),
        ("bse_mapping", {}),
    ]:
        rows = provider.all(api, **params)
        if not rows and api not in ("suspend_d", "bse_mapping"):
            raise ProviderError(f"{api} 返回空数据")
        results["checks"][api] = len(rows)
    members = provider.all("index_member_all", l1_code="801780.SI", is_new="Y")
    if not members:
        raise ProviderError("SW2021 行业成分为空")
    results["checks"]["index_member_all"] = len(members)
    for api, params in [
        ("stock_st", {"trade_date": date}),
        ("stock_company", {"exchange": "BSE"}),
    ]:
        try:
            results["checks"][api] = len(provider.all(api, **params))
        except ProviderError as exc:
            results["checks"][api] = f"可选数据不可用：{exc}"
    return results


def main():
    parser = argparse.ArgumentParser(description="A 股看板数据工具")
    parser.add_argument(
        "command",
        choices=[
            "migrate",
            "collect-business", "build-industry-chains", "publish-chain-batch",
            "update-industry-chains", "doctor-chain-updates",
            "validate-chain", "import-chain", "review-chain", "publish-chain", "doctor-chain",
            "doctor",
            "bootstrap",
            "sync",
            "backfill",
            "sync-leaders",
            "sync-concepts",
            "sync-concepts-em",
            "backup",
            "refresh-quotes",
            "doctor-fund-flow",
            "sync-fund-flow",
        ],
    )
    parser.add_argument("--start", type=valid_date)
    parser.add_argument("--end", type=valid_date)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--output")
    parser.add_argument("--provider", choices=["free", "tushare"], default=data_provider())
    parser.add_argument("--history-limit", type=int, help="限制本次历史回填股票数，0 只更新行情")
    parser.add_argument("--codes", help="历史回填指定代码，以逗号分隔，例如 600519.SH,920000.BJ")
    parser.add_argument("--concept", help="只同步指定名称的概念板块，例如 固态电池")
    parser.add_argument("--fund-kind", choices=["all", "concept", "industry"], default="all")
    parser.add_argument("--fund-period", choices=["all", "today", "5d", "10d"], default="all")
    parser.add_argument("--fund-board", help="同步同源板块历史和成分资金，例如 EM-concept-BK1136")
    parser.add_argument("--chain-file", help="产业链 JSON 内容包路径")
    parser.add_argument("--chain-revision", help="产业链内容版本 ID")
    parser.add_argument("--chain-reviewer", help="资料核验人（如实填写）")
    parser.add_argument("--chain-review-note", help="资料核验范围、依据及缺口说明")
    parser.add_argument("--direct-network", action="store_true", help="公开业务接口直连，不使用环境代理")
    args = parser.parse_args()
    if args.command in ("update-industry-chains", "doctor-chain-updates"):
        from app.chain_updates import status, update
        migrate()
        if args.command == "doctor-chain-updates":
            with Session() as s:
                report(status(s))
            return 0
        result = update(Session, force=args.force, direct=args.direct_network)
        # Snapshot selections are internal audit data, not CLI output.
        report(result)
        return 1 if result["state"] in ("failed", "busy") else 0
    if args.command in ("collect-business", "build-industry-chains", "publish-chain-batch"):
        migrate()
        if args.command == "collect-business":
            from app.jobs.business_collection import collect
            report(collect(Session, direct=args.direct_network, refresh=args.force))
        elif args.command == "publish-chain-batch":
            from app.jobs.chain_supplement import publish_batch
            report(publish_batch(Session, args.chain_file, args.chain_reviewer, args.chain_review_note))
        else:
            from app.jobs.chain_supplement import build_all
            report(build_all(Session))
        return 0
    if args.command.endswith("-chain"):
        from app.jobs.industry_chains import maintain
        try:
            if args.command != "validate-chain":
                migrate()
            report(maintain(args.command, Session, args.chain_file, args.chain_revision, args.chain_reviewer, args.chain_review_note))
            return 0
        except (ValueError, OSError) as exc:
            report({"ok": False, "error": str(exc)})
            return 1
    if args.history_limit is not None and args.history_limit < 0:
        parser.error("--history-limit 不能为负数")
    provider_class = FreeProvider if args.provider == "free" else Tushare
    last_date = free_cutoff if args.provider == "free" else cutoff
    if args.command == "doctor-fund-flow":
        from app.providers.fund_flow import FundFlowProvider

        fund_provider = FundFlowProvider()
        checks = []
        try:
            for kind in ("concept", "industry") if args.fund_kind == "all" else (args.fund_kind,):
                for period in ("today", "5d", "10d") if args.fund_period == "all" else (args.fund_period,):
                    data = fund_provider.listing(kind, period)
                    checks.append({"kind": kind, "period": period, "rows": data["total"], "trade_date": data["trade_date"], "source_as_of": data["source_as_of"]})
            report({"ok": True, "checks": checks})
            return 0
        except Exception as exc:
            report({"ok": False, "error": str(exc) if isinstance(exc, ProviderError) else type(exc).__name__, "checks": checks})
            return 1
        finally:
            fund_provider.close()
    if args.command == "doctor":
        try:
            provider = provider_class()
            try:
                result = provider.doctor() if args.provider == "free" else doctor(provider)
                report(result)
                if result.get("ok") is False:
                    return 1
            finally:
                provider.close()
        except ProviderError as exc:
            report({"ok": False, "error": str(exc)})
            return 1
        return 0
    if args.command == "backup":
        if not args.output:
            parser.error("backup 需要 --output")
        destination = Path(args.output).resolve()
        if destination == db_path().resolve() or destination.exists():
            parser.error("备份目标必须是新的文件")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with (
            sqlite3.connect(db_path()) as source,
            sqlite3.connect(destination) as target,
        ):
            source.backup(target)
        report({"backup": str(destination)})
        return 0
    migrate()
    if args.command == "migrate":
        report({"ok": True})
        return 0
    if args.command == "sync-fund-flow":
        from app.fund_flow import collect
        from app.models import FundBoard

        results = []
        periods = ("today", "5d", "10d") if args.fund_period == "all" else (args.fund_period,)
        if args.fund_board:
            with Session() as session:
                fund_board = session.get(FundBoard, args.fund_board)
                if not fund_board:
                    report({"ok": False, "error": "板块尚未注册，请先同步排行"})
                    return 1
                kind, code = fund_board.kind, fund_board.code
            results.append(collect(kind, "daily", code, "history", force=args.force))
            results.extend(collect(kind, p, code, "stocks", force=args.force) for p in periods)
        else:
            for kind in ("concept", "industry") if args.fund_kind == "all" else (args.fund_kind,):
                results.extend(collect(kind, p, force=args.force) for p in periods)
        ok = not any(r.get("error") for r in results)
        report({"ok": ok, "results": results})
        return 0 if ok else 1
    if args.command == "refresh-quotes":
        from app.realtime import refresh

        try:
            value = refresh()
            report({"ok": True, **{k: v for k, v in (value or {}).items() if k != "quotes"}})
            return 0
        except ProviderError as exc:
            report({"ok": False, "error": str(exc)})
            return 1
    provider, run_id = None, None
    try:
        with sync_lock():
            if args.command == "sync-leaders":
                provider = FreeProvider()
                report(refresh_index_leaders(provider))
                return 0
            if args.command == "sync-concepts-em":
                provider = FreeProvider()
                result = sync_concepts(provider, name=args.concept, progress=print)
                report(result)
                return 1 if result["failures"] else 0
            if args.command == "sync-concepts":
                if args.concept:
                    raise ProviderError("通达信概念按全量文件同步；请去掉 --concept")
                result = sync_tdx_concepts(progress=print)
                report(result)
                return 0
            provider = provider_class()
            end = args.end or last_date()
            start = args.start or (datetime.strptime(end, "%Y%m%d") - timedelta(days=366)).strftime(
                "%Y%m%d"
            )
            if start > end or end > last_date():
                raise ProviderError("日期范围无效，结束日期不得超过最近可同步日期")
            with Session.begin() as session:
                for old in session.scalars(select(SyncRun).where(SyncRun.state == "running")):
                    old.state, old.ended_at, old.error = (
                        "interrupted",
                        utcnow(),
                        "上次任务中断，已重新取得同步锁",
                    )
                run = SyncRun(command=args.command)
                session.add(run)
                session.flush()
                run_id = run.id

            def progress(message):
                print(message, flush=True)
                with Session.begin() as session:
                    session.get(SyncRun, run_id).progress = message

            if args.provider == "free":
                if (
                    datetime.strptime(end, "%Y%m%d") - datetime.strptime(start, "%Y%m%d")
                ).days > 3660:
                    raise ProviderError("免费历史单次最多支持十年；请将日期区间控制在 3660 天内")
                service = FreeSyncService(provider, progress=progress)
                limit = args.history_limit
                if limit is None and args.command != "backfill":
                    limit = 100 if args.command == "bootstrap" else 20
                result = service.run(
                    start,
                    end,
                    args.force,
                    command=args.command,
                    limit=limit,
                    codes=args.codes.split(",") if args.codes else None,
                )
            else:
                service = SyncService(provider, progress=progress)
                result = service.run(start, end, args.force)
            if args.command != "backfill":
                leader_provider = provider if args.provider == "free" else FreeProvider()
                try:
                    leaders = refresh_index_leaders(leader_provider, progress=progress)
                    result["leaders"] = leaders
                    result["warnings"].extend(leaders["warnings"])
                finally:
                    if leader_provider is not provider:
                        leader_provider.close()
                try:
                    concepts = sync_tdx_concepts(progress=progress)
                    result["concepts"] = concepts
                    result["warnings"].extend(concepts["failures"])
                except Exception as exc:
                    result["warnings"].append(f"概念板块同步失败，保留旧名单：{exc}")
            with Session.begin() as session:
                run = session.get(SyncRun, run_id)
                run.state = "partial" if result["failures"] else "complete"
                run.ended_at = utcnow()
                run.error = "\n".join(result["failures"]) or None
                run.warnings = json.dumps(result["warnings"], ensure_ascii=False)
            report(result)
            return 1 if result["failures"] else 0
    except Exception as exc:
        message = str(exc)
        if token():
            message = message.replace(token(), "[redacted]")
        if run_id:
            with Session.begin() as session:
                run = session.get(SyncRun, run_id)
                run.state, run.error, run.ended_at = "failed", message, utcnow()
        report({"ok": False, "error": message})
        return 1
    finally:
        if provider:
            provider.close()


if __name__ == "__main__":
    sys.exit(main())
