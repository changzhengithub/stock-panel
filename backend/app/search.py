"""Global discovery is independent of the current market filters."""

from functools import lru_cache

from pypinyin import Style, lazy_pinyin
from sqlalchemy import select

from app.models import Stock
from app.universe import visible_stock


@lru_cache(maxsize=20000)
def spellings(name):
    return (
        "".join(lazy_pinyin(name)).lower(),
        "".join(lazy_pinyin(name, style=Style.FIRST_LETTER)).lower(),
    )


def search_stocks(session, keyword):
    key = keyword.strip().lower()
    if not key:
        return []
    found = []
    for stock in session.scalars(select(Stock).where(visible_stock())):
        candidates = (
            stock.symbol,
            stock.ts_code.lower(),
            stock.name.lower(),
            *spellings(stock.name),
        )
        if any(key in value for value in candidates):
            score = (
                0
                if key in candidates[:3]
                else 1
                if any(value.startswith(key) for value in candidates)
                else 2
            )
            found.append((score, stock.symbol, stock))
    return [
        dict(id=s.id, code=s.symbol, ts_code=s.ts_code, name=s.name, board=s.board)
        for _, _, s in sorted(found, key=lambda r: (r[0], r[1], r[2].exchange))[:20]
    ]
