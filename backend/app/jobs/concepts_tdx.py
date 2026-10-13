"""Publish validated concept memberships from the Tongdaxin block file."""

import asyncio
import re

from pytdxdata import TdxData
from sqlalchemy import delete, select

from app.db import Session
from app.models import Concept, ConceptMember, Stock, utcnow
from app.providers.tushare import ProviderError

SOURCE = "通达信公开概念板块"
BLOCK_FILE = "block_gn.dat"
BLOCK_MEMBER_LIMIT = 400


async def fetch_blocks():
    async with TdxData() as client:
        return await asyncio.wait_for(client.get_block_parsed(BLOCK_FILE), timeout=45)


def sync_tdx_concepts(
    sessions=Session, progress=None, blocks=None, minimum_catalog_size=200,
):
    progress = progress or (lambda _: None)
    try:
        blocks = blocks if blocks is not None else asyncio.run(fetch_blocks())
    except Exception as exc:
        raise ProviderError(f"通达信概念文件获取失败：{exc}") from exc
    if len(blocks) < minimum_catalog_size:
        raise ProviderError(f"通达信概念目录仅 {len(blocks)} 个，拒绝发布")
    with sessions() as session:
        stocks = session.execute(
            select(Stock.symbol, Stock.id).where(Stock.list_status == "L")
        ).all()
    stock_ids = dict(stocks)
    names, members, limited = set(), {}, []
    for block in blocks:
        name = str(block.name).strip()
        codes = list(block.codes)
        if not name or name in names or block.count != len(codes) or len(set(codes)) != len(codes):
            raise ProviderError("通达信概念目录有重复名称或成分数量不一致")
        names.add(name)
        if any(not re.fullmatch(r"\d{6}", code) for code in codes):
            raise ProviderError(f"{name} 有无效股票代码")
        if len(codes) >= BLOCK_MEMBER_LIMIT:
            limited.append(name)
            continue
        ids = {stock_ids[code] for code in codes if code in stock_ids}
        if not ids or len(ids) < len(codes) * 0.8:
            raise ProviderError(f"{name} 成分与本地 A 股匹配不足，拒绝发布")
        members[name] = ids
    if len(members) < minimum_catalog_size * 0.8:
        raise ProviderError("通达信概念可发布数量异常，保留旧名单")
    progress(f"通达信概念校验完成：{len(members)} 个可发布，{len(limited)} 个达到源文件上限")
    fetched_at = utcnow()
    with sessions.begin() as session:
        for name, ids in members.items():
            concept_id = f"TDX:{name}"
            board = session.get(Concept, concept_id)
            if board is None:
                board = Concept(id=concept_id, name=name, source=SOURCE)
                session.add(board)
            session.execute(delete(ConceptMember).where(ConceptMember.concept_id == concept_id))
            session.add_all(
                ConceptMember(concept_id=concept_id, stock_id=stock_id) for stock_id in ids
            )
            board.name, board.source = name, SOURCE
            board.fetched_at, board.error = fetched_at, None
        for name in limited:
            concept_id = f"TDX:{name}"
            board = session.get(Concept, concept_id)
            if board is None:
                session.add(Concept(
                    id=concept_id, name=name, source=SOURCE,
                    error="源文件成分达到 400 只上限，可能被截断",
                ))
            else:
                board.error = "源文件成分达到 400 只上限，保留上次有效名单"
    return {
        "source": SOURCE, "boards": len(blocks), "updated": len(members),
        "memberships": sum(map(len, members.values())),
        "limited": limited, "failures": [],
    }
