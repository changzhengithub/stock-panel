from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class Base(DeclarativeBase):
    pass


class Industry(Base):
    __tablename__ = "industries"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str]
    source: Mapped[str] = mapped_column(default="SW2021 L1")


class Stock(Base):
    __tablename__ = "stocks"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts_code: Mapped[str] = mapped_column(unique=True)
    symbol: Mapped[str] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(index=True)
    exchange: Mapped[str]
    board: Mapped[str]
    industry_id: Mapped[str] = mapped_column(
        ForeignKey("industries.id"), default="unclassified", index=True
    )
    list_date: Mapped[str]
    delist_date: Mapped[str | None]
    list_status: Mapped[str] = mapped_column(default="L", index=True)
    fullname: Mapped[str | None]
    introduction: Mapped[str | None] = mapped_column(Text)
    main_business: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[str] = mapped_column(default=utcnow)


class CodeAlias(Base):
    __tablename__ = "code_aliases"
    code: Mapped[str] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)


class Representative(Base):
    __tablename__ = "industry_representatives"
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), primary_key=True)
    industry_id: Mapped[str] = mapped_column(ForeignKey("industries.id"), index=True)
    position: Mapped[int]
    reason: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str]
    reviewed_at: Mapped[str]


class Quote(Base):
    __tablename__ = "daily_quotes"
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), primary_key=True)
    trade_date: Mapped[str] = mapped_column(primary_key=True)
    close: Mapped[float | None]
    pct_chg: Mapped[float | None]
    amount: Mapped[float | None]
    market_cap: Mapped[float | None]
    status: Mapped[str] = mapped_column(default="trading")
    is_st: Mapped[bool | None]
    st_source: Mapped[str] = mapped_column(default="unavailable")
    __table_args__ = (Index("ix_quotes_date_pct", "trade_date", "pct_chg"),)


class Factor(Base):
    __tablename__ = "adjustment_factors"
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), primary_key=True)
    trade_date: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[float]


class Calendar(Base):
    __tablename__ = "trading_calendar"
    exchange: Mapped[str] = mapped_column(primary_key=True)
    date: Mapped[str] = mapped_column(primary_key=True)
    is_open: Mapped[bool]
    source: Mapped[str]


class Publication(Base):
    __tablename__ = "publications"
    trade_date: Mapped[str] = mapped_column(primary_key=True)
    published_at: Mapped[str] = mapped_column(default=utcnow)
    stock_count: Mapped[int]


class SyncRun(Base):
    __tablename__ = "sync_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    command: Mapped[str]
    state: Mapped[str] = mapped_column(default="running")
    started_at: Mapped[str] = mapped_column(default=utcnow)
    ended_at: Mapped[str | None]
    progress: Mapped[str] = mapped_column(default="准备同步")
    error: Mapped[str | None] = mapped_column(Text)
    warnings: Mapped[str] = mapped_column(Text, default="[]")


class SyncDay(Base):
    __tablename__ = "sync_days"
    trade_date: Mapped[str] = mapped_column(primary_key=True)
    state: Mapped[str]
    error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[str] = mapped_column(default=utcnow)
