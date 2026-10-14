"""Persistent, single-writer automatic acquisition and atomic industry publication."""

import hashlib
import json
import logging
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select

from app.business_models import ChainUpdateRun
from app.chain_models import ChainRevision, IndustryChain
from app.chain_service import digest
from app.jobs.business_collection import collect, collection_periods, snapshots
from app.jobs.chain_supplement import build_all, publish_batch
from app.jobs.industry_chains import chain_lock
from app.models import Industry, Stock, utcnow
from app.settings import ROOT, db_path
from app.universe import visible_stock

TZ = ZoneInfo("Asia/Shanghai")
log = logging.getLogger(__name__)
SUCCESS = ("published", "unchanged")


def enabled():
    return os.getenv("CHAIN_AUTO_UPDATE", "1") != "0"


def interval_hours():
    return max(1, int(os.getenv("CHAIN_UPDATE_INTERVAL_HOURS", "24")))


def policy():
    return json.loads((ROOT / "config/industry_models/maintenance.json").read_text())


def model_signature():
    paths = list((ROOT / "config/industry_models").glob("*")) + [
        Path(__file__),
        ROOT / "backend/app/business_analysis.py",
        ROOT / "backend/app/jobs/chain_supplement.py",
        ROOT / "backend/app/jobs/business_collection.py",
    ]
    return digest(
        {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths)
            if p.is_file()
        }
    )


def input_signature(factory, model_hash):
    with factory() as s:
        facts = snapshots(s)
        stocks = list(s.scalars(select(Stock).where(visible_stock(s)).order_by(Stock.ts_code)))
        industries = [
            (x.id, x.name, x.level, x.parent_id)
            for x in s.scalars(select(Industry).order_by(Industry.id))
        ]
    return digest(
        dict(
            models=model_hash,
            periods=collection_periods(),
            industries=industries,
            companies=[
                (
                    x.ts_code,
                    x.name,
                    x.industry_id,
                    x.industry_l2_id,
                    digest(
                        {k: v for k, v in facts[x.ts_code].payload.items() if k != "collected_at"}
                    )
                    if x.ts_code in facts
                    else None,
                )
                for x in stocks
            ],
        )
    )


def last_run(s, success=False):
    query = select(ChainUpdateRun)
    if success:
        query = query.where(ChainUpdateRun.state.in_(SUCCESS))
    return s.scalar(
        query.order_by(ChainUpdateRun.started_at.desc(), ChainUpdateRun.id.desc()).limit(1)
    )


def next_check(run):
    if not run:
        return datetime.now(TZ)
    stamp = datetime.fromisoformat(run.finished_at or run.started_at)
    hours = 1 if run.state in ("failed", "interrupted") else interval_hours()
    return stamp + timedelta(hours=hours)


def status(s):
    run, good = last_run(s), last_run(s, success=True)
    rules = policy()
    review_due = datetime.fromisoformat(rules["logic_reviewed_on"]).replace(tzinfo=TZ) + timedelta(
        days=rules["logic_review_interval_days"]
    )
    return dict(
        enabled=enabled(),
        interval_hours=interval_hours(),
        state=run.state if run else "pending",
        started_at=run.started_at if run else None,
        finished_at=run.finished_at if run else None,
        last_success_at=good.finished_at if good else None,
        next_check_at=next_check(run).isoformat() if enabled() else None,
        error=run.payload.get("error") if run else None,
        phase=run.payload.get("phase") if run else None,
        published_count=run.payload.get("published_count", 0) if run else 0,
        logic_reviewed_on=rules["logic_reviewed_on"],
        logic_review_due_on=review_due.date().isoformat(),
        logic_review_overdue=datetime.now(TZ) >= review_due,
        maintenance=(run.payload.get("maintenance") if run else None)
        or (good.payload.get("maintenance") if good else None),
        periods=(good.payload.get("periods", []) if good else []),
    )


def period_end(period):
    try:
        year, suffix = period.split("-", 1) if "-" in period else (period, "FY")
        month, day = {"FY": (12, 31), "H1": (6, 30), "Q1": (3, 31), "Q3": (9, 30)}[suffix]
        return f"{int(year):04d}-{month:02d}-{day:02d}"
    except (ValueError, KeyError, TypeError):
        return ""


def maintenance_inventory(factory):
    """Detect expired leader periods across all published industries and curated topics."""
    tasks, sources = [], {}
    latest_period = max(collection_periods())
    with factory() as s:
        revisions = s.scalars(
            select(ChainRevision).join(
                IndustryChain, IndustryChain.published_revision == ChainRevision.id
            )
        )
        for r in revisions:
            source_map = {x["id"]: x for x in r.payload["sources"]}
            for link in r.payload["stocks"]:
                for claim in link["leaders"]:
                    if period_end(claim["period"]) < latest_period:
                        tasks.append(
                            dict(
                                chain_id=r.chain_id,
                                ts_code=link["ts_code"],
                                node=link["node"],
                                period=claim["period"],
                                reason="龙头依据早于最新目标报告期，需复核",
                            )
                        )
                    for e in claim["evidence"]:
                        src = source_map[e["source_id"]]
                        sources[src["url"]] = src
    return tasks, sources


def probe_evidence(sources, *, direct=False, stop=None):
    """Check source accessibility and byte changes; never infer semantic verification."""
    checks = []
    with httpx.Client(timeout=20, trust_env=not direct, follow_redirects=True) as client:
        for url, src in sources.items():
            if stop and stop.is_set():
                raise ValueError("服务停止，取消证据检查")
            result = dict(url=url, source_id=src["id"], checked_at=utcnow())
            try:
                sha, size = hashlib.sha256(), 0
                with client.stream("GET", url) as response:
                    response.raise_for_status()
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > 30_000_000:
                            raise ValueError("证据文件超过检查大小限制")
                        sha.update(chunk)
                result["observed_hash"] = sha.hexdigest()
                expected = src.get("snapshot_hash")
                result["state"] = (
                    ("unchanged" if expected == sha.hexdigest() else "changed")
                    if expected
                    else "needs_review"
                )
            except (httpx.HTTPError, ValueError) as exc:
                result.update(state="unavailable", error=str(exc)[:300])
            checks.append(result)
    return checks


def check_maintenance(factory, previous=None, *, direct=False, stop=None):
    tasks, sources = maintenance_inventory(factory)
    previous = previous or {}
    stamp = previous.get("evidence_checked_at")
    prior_urls = {x["url"] for x in previous.get("source_checks", [])}
    due = (
        set(sources) != prior_urls
        or not stamp
        or datetime.now(TZ)
        >= datetime.fromisoformat(stamp) + timedelta(days=policy()["evidence_check_interval_days"])
    )
    checks = (
        probe_evidence(sources, direct=direct, stop=stop)
        if due
        else previous.get("source_checks", [])
    )
    # A source hash match validates byte stability, not the truth or currency of its claims.
    return dict(
        leader_review_count=len(tasks),
        leader_reviews=tasks,
        evidence_checked_at=utcnow() if due else stamp,
        source_checks=checks,
        source_review_count=sum(x["state"] != "unchanged" for x in checks),
    )


def update(factory, *, force=False, direct=False, stop=None, output=None):
    try:
        with chain_lock():
            return _update(factory, force=force, direct=direct, stop=stop, output=output)
    except BlockingIOError:
        return dict(state="busy", reason="已有产业分析维护任务运行")


def _update(factory, *, force=False, direct=False, stop=None, output=None):
    model_hash = model_signature()
    with factory() as s:
        previous, good = last_run(s), last_run(s, success=True)
    if (
        not force
        and previous
        and previous.state != "running"
        and datetime.now(TZ) < next_check(previous)
    ):
        # Failed inputs wait for retry; a subsequent rule edit triggers another attempt.
        if previous.payload.get("model_signature") == model_hash:
            return dict(state="not_due")
    run_id = uuid4().hex
    payload = dict(phase="collecting", model_signature=model_hash)
    with factory.begin() as s:
        # Owning the file lock proves that an older running record has lost its writer.
        for orphan in s.scalars(select(ChainUpdateRun).where(ChainUpdateRun.state == "running")):
            orphan.state, orphan.finished_at = "interrupted", utcnow()
            orphan.payload = {**orphan.payload, "error": "上一轮进程停止，重新采集后再发布"}
        s.add(ChainUpdateRun(id=run_id, state="running", payload=payload))

    def phase(name):
        payload["phase"] = name
        with factory.begin() as s:
            s.get(ChainUpdateRun, run_id).payload = dict(payload)

    try:
        report = collect(factory, direct=direct, refresh=True, strict=True, stop=stop)
        payload.update(
            periods=report["periods"],
            collected_at=report["collected_at"],
            business_count=report["business_count"],
            financial_count=report["financial_count"],
        )
        signature = input_signature(factory, model_hash)
        payload["input_signature"] = signature
        phase("checking_evidence")
        payload["maintenance"] = check_maintenance(
            factory, good.payload.get("maintenance") if good else None, direct=direct, stop=stop
        )
        # Failed builds cannot leave their new business snapshots looking like a successful update.
        with factory() as s:
            missing = s.scalar(
                select(IndustryChain.id)
                .where(IndustryChain.id.like("sw-%"), IndustryChain.published_revision.is_(None))
                .limit(1)
            )
        if good and good.payload.get("input_signature") == signature and not missing:
            state = "unchanged"
            payload["published_count"] = 0
        else:
            phase("building")
            directory = Path(output or db_path().parent / "industry-chain-updates" / run_id)
            manifest = build_all(factory, directory)
            if stop and stop.is_set():
                raise ValueError("服务停止，取消本轮发布")
            if model_signature() != model_hash:
                raise ValueError("生成期间规则发生变化，保留旧版，下一轮重新生成")
            if input_signature(factory, model_hash) != signature:
                raise ValueError("生成期间股票池或资料变化，保留旧版，下一轮重新生成")
            if any(
                x.get("analysis_version") != 2 or not x.get("analysis_audit", {}).get("passed")
                for x in manifest["items"]
            ):
                raise ValueError("全行业专属分析校验未通过")
            phase("publishing")
            result = publish_batch(
                factory,
                directory / "manifest.json",
                "自动结构校验",
                "公开数据商采集、全行业结构与分析规则自动校验；原始公告和龙头事实仍按各项证据标注，不等于人工核验。",
            )
            payload["published_count"] = result["published_count"]
            from app.chain_service import search_terms

            search_terms.cache_clear()
            state = "published"
        payload["phase"] = "complete"
        with factory.begin() as s:
            run = s.get(ChainUpdateRun, run_id)
            run.state, run.finished_at, run.payload = state, utcnow(), payload
        return dict(run_id=run_id, state=state, **payload)
    except Exception as exc:
        payload["error"] = str(exc)[:1200]
        with factory.begin() as s:
            run = s.get(ChainUpdateRun, run_id)
            run.state, run.finished_at, run.payload = "failed", utcnow(), payload
        log.exception("产业分析自动更新失败，保留已发布版本")
        return dict(run_id=run_id, state="failed", **payload)


def start_worker():
    from app.db import Session

    stop = threading.Event()
    if not enabled():
        return stop

    def work():
        while not stop.is_set():
            try:
                update(
                    Session, direct=os.getenv("CHAIN_UPDATE_DIRECT_NETWORK", "0") == "1", stop=stop
                )
            except Exception:
                log.exception("产业分析更新调度异常")
            stop.wait(60)

    threading.Thread(target=work, name="industry-analysis-updates", daemon=True).start()
    return stop
