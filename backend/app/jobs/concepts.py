"""Publish independently validated Eastmoney concept memberships."""

import re

from sqlalchemy import delete, select

from app.db import Session
from app.models import Concept, ConceptMember, Stock, utcnow
from app.providers.tushare import ProviderError

SOURCE = "东方财富概念板块 / AKShare"


def sync_concepts(
    provider, sessions=Session, name=None, progress=None, max_consecutive_failures=3,
    minimum_catalog_size=100,
):
    progress = progress or (lambda _: None)
    rows = provider.ak("stock_board_concept_name_em")
    boards = {}
    for row in rows:
        code, label = str(row.get("板块代码", "")).strip(), str(row.get("板块名称", "")).strip()
        if not re.fullmatch(r"BK\d{4,6}", code) or not label or code in boards:
            raise ProviderError("概念板块目录存在无效代码、空名称或重复代码")
        boards[code] = label
    if len(boards) < minimum_catalog_size:
        raise ProviderError("概念板块目录数量异常，拒绝发布不完整目录")
    if name and name not in boards.values():
        raise ProviderError(f"概念板块不存在：{name}")
    with sessions() as session:
        previous_count = session.query(Concept).count()
    if previous_count and len(boards) < previous_count * 0.8:
        raise ProviderError("概念板块目录较上次大幅减少，拒绝覆盖旧目录")
    with sessions.begin() as session:
        for code, label in boards.items():
            board = session.get(Concept, code)
            if board:
                board.name = label
            else:
                session.add(Concept(id=code, name=label, source=SOURCE))
    selected = [(code, label) for code, label in boards.items() if not name or label == name]
    success, failures, consecutive_failures = 0, [], 0
    for index, (code, label) in enumerate(selected, 1):
        progress(f"概念成分 {index}/{len(selected)}：{label}")
        try:
            members = provider.ak("stock_board_concept_cons_em", symbol=code)
            symbols = set()
            for row in members:
                symbol = str(row.get("代码", "")).strip().zfill(6)
                if not re.fullmatch(r"\d{6}", symbol) or symbol in symbols:
                    raise ProviderError(f"{label} 成分代码无效或重复")
                symbols.add(symbol)
            with sessions.begin() as session:
                stocks = list(session.scalars(select(Stock).where(Stock.symbol.in_(symbols))))
                ids = {stock.id for stock in stocks}
                # Provider lists can contain inactive or non-A-share securities, but a
                # completely unmatched list indicates a broken source or stock universe.
                if not ids or len(ids) < len(symbols) * 0.8:
                    raise ProviderError(f"{label} 成分与本地 A 股匹配不足，拒绝覆盖旧名单")
                session.execute(delete(ConceptMember).where(ConceptMember.concept_id == code))
                session.add_all(ConceptMember(concept_id=code, stock_id=stock_id) for stock_id in ids)
                board = session.get(Concept, code)
                board.fetched_at, board.error = utcnow(), None
            success += 1
            consecutive_failures = 0
        except Exception as exc:
            message = f"{label}: {exc}"
            failures.append(message)
            with sessions.begin() as session:
                session.get(Concept, code).error = str(exc)
            consecutive_failures += 1
            if consecutive_failures >= max_consecutive_failures:
                failures.append("概念来源连续失败，已停止本轮并保留其余旧名单")
                break
    return {"boards": len(boards), "updated": success, "failures": failures}
