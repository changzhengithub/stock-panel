"""Immutable revisions and normalized graph references; payloads follow strict schema."""

from sqlalchemy import JSON, ForeignKey, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, utcnow


class IndustryChain(Base):
    __tablename__ = "industry_chains"
    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    published_revision: Mapped[str | None]


class ChainRevision(Base):
    __tablename__ = "chain_revisions"
    id: Mapped[str] = mapped_column(primary_key=True)
    chain_id: Mapped[str] = mapped_column(ForeignKey("industry_chains.id"), index=True)
    content_hash: Mapped[str]
    payload: Mapped[dict] = mapped_column(JSON)
    catalog: Mapped[dict | None] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(default="validated")
    created_at: Mapped[str] = mapped_column(default=utcnow)
    reviewed_at: Mapped[str | None]
    reviewer: Mapped[str | None]
    review_note: Mapped[str | None]
    published_at: Mapped[str | None]
    __table_args__ = (UniqueConstraint("chain_id", "content_hash"),)


class ChainNode(Base):
    __tablename__ = "chain_nodes"
    revision_id: Mapped[str] = mapped_column(ForeignKey("chain_revisions.id"), primary_key=True)
    key: Mapped[str] = mapped_column(primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)


class ChainEdge(Base):
    __tablename__ = "chain_edges"
    revision_id: Mapped[str] = mapped_column(ForeignKey("chain_revisions.id"), primary_key=True)
    key: Mapped[str] = mapped_column(primary_key=True)
    source: Mapped[str]
    target: Mapped[str]
    payload: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        ForeignKeyConstraint(
            ["revision_id", "source"], ["chain_nodes.revision_id", "chain_nodes.key"]
        ),
        ForeignKeyConstraint(
            ["revision_id", "target"], ["chain_nodes.revision_id", "chain_nodes.key"]
        ),
    )


class ChainStockLink(Base):
    __tablename__ = "chain_stock_links"
    revision_id: Mapped[str] = mapped_column(ForeignKey("chain_revisions.id"), primary_key=True)
    key: Mapped[str] = mapped_column(primary_key=True)
    node_key: Mapped[str]
    ts_code: Mapped[str] = mapped_column(index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        ForeignKeyConstraint(
            ["revision_id", "node_key"], ["chain_nodes.revision_id", "chain_nodes.key"]
        ),
    )


class ChainSource(Base):
    __tablename__ = "chain_sources"
    revision_id: Mapped[str] = mapped_column(ForeignKey("chain_revisions.id"), primary_key=True)
    key: Mapped[str] = mapped_column(primary_key=True)
    snapshot_hash: Mapped[str]
    payload: Mapped[dict] = mapped_column(JSON)


class ChainEvidence(Base):
    __tablename__ = "chain_evidence"
    revision_id: Mapped[str] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(primary_key=True)
    source_key: Mapped[str]
    target_kind: Mapped[str]
    target_key: Mapped[str]
    payload: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        ForeignKeyConstraint(
            ["revision_id", "source_key"], ["chain_sources.revision_id", "chain_sources.key"]
        ),
    )


class ChainAnalysis(Base):
    __tablename__ = "chain_analyses"
    revision_id: Mapped[str] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(primary_key=True)
    node_key: Mapped[str]
    payload: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        ForeignKeyConstraint(
            ["revision_id", "node_key"], ["chain_nodes.revision_id", "chain_nodes.key"]
        ),
    )


class ChainBusinessMetric(Base):
    __tablename__ = "chain_business_metrics"
    revision_id: Mapped[str] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(primary_key=True)
    link_key: Mapped[str]
    payload: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        ForeignKeyConstraint(
            ["revision_id", "link_key"], ["chain_stock_links.revision_id", "chain_stock_links.key"]
        ),
    )


class ChainLeaderClaim(Base):
    __tablename__ = "chain_leader_claims"
    revision_id: Mapped[str] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(primary_key=True)
    link_key: Mapped[str]
    payload: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        ForeignKeyConstraint(
            ["revision_id", "link_key"], ["chain_stock_links.revision_id", "chain_stock_links.key"]
        ),
    )


class ChainImportRun(Base):
    __tablename__ = "chain_import_runs"
    id: Mapped[str] = mapped_column(primary_key=True)
    chain_id: Mapped[str]
    input_hash: Mapped[str]
    revision_id: Mapped[str | None]
    state: Mapped[str]
    started_at: Mapped[str] = mapped_column(default=utcnow)
    finished_at: Mapped[str | None]
    error: Mapped[str | None]
