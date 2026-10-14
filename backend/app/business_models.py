"""Public vendor snapshots. These do not constitute independently reviewed business facts."""

from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, utcnow


class BusinessSnapshot(Base):
    __tablename__ = "business_snapshots"
    ts_code: Mapped[str] = mapped_column(primary_key=True)
    content_hash: Mapped[str] = mapped_column(primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)
    collected_at: Mapped[str] = mapped_column(default=utcnow, index=True)


class BusinessCollection(Base):
    __tablename__ = "business_collections"
    id: Mapped[str] = mapped_column(primary_key=True)
    state: Mapped[str]
    started_at: Mapped[str] = mapped_column(default=utcnow)
    finished_at: Mapped[str | None]
    payload: Mapped[dict] = mapped_column(JSON)


class ChainUpdateRun(Base):
    __tablename__ = "chain_update_runs"
    id: Mapped[str] = mapped_column(primary_key=True)
    state: Mapped[str]
    started_at: Mapped[str] = mapped_column(default=utcnow, index=True)
    finished_at: Mapped[str | None]
    payload: Mapped[dict] = mapped_column(JSON)
