from typing import Literal

from pydantic import BaseModel


class RepresentativeInfo(BaseModel):
    reason: str
    source_url: str
    reviewed_at: str
    weight_date: str | None = None
    industry_level: Literal[1, 2] = 1


class StockInfo(BaseModel):
    profile_pending: bool = False
    id: int
    code: str
    ts_code: str
    name: str
    industry_id: str
    industry: str
    industry_l2_id: str | None
    industry_l2: str | None
    board: str
    exchange: str
    list_date: str
    fullname: str | None
    introduction: str | None
    main_business: str | None
    updated_at: str
    close: float | None
    pct_chg: float | None
    amount: float | None
    market_cap: float | None
    float_market_cap: float | None
    turnover_rate: float | None
    pe_ratio: float | None
    pe_basis: str | None
    pb_ratio: float | None
    total_shares: float | None
    float_shares: float | None
    quote_date: str | None
    status: Literal["trading", "suspended", "unavailable"]
    is_st: bool
    st_source: str
    representative: RepresentativeInfo | None


class IndustryInfo(BaseModel):
    id: str
    name: str
    level: Literal[1, 2] = 1
    parent_id: str | None = None
    parent_name: str | None = None
    stock_count: int
    representative_count: int


class ConceptInfo(BaseModel):
    id: str
    name: str
    stock_count: int
    source: str
    fetched_at: str | None
    error: str | None


class IndustryGroup(BaseModel):
    id: str
    name: str
    stock_count: int
    items: list[StockInfo]


class StockList(BaseModel):
    navigation: dict | None = None
    items: list[StockInfo]
    groups: list[IndustryGroup]
    total: int
    matched_stocks: int
    pagination_unit: Literal["stock", "industry"]
    page: int
    page_size: int
    trade_date: str | None


class PricePoint(BaseModel):
    status: Literal["trading", "suspended", "missing"] = "trading"
    date: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None


class PriceSeries(BaseModel):
    points: list[PricePoint]
    basis_date: str | None
    adjustment: Literal["qfq", "none"]
    start_date: str | None = None
    stale: bool = False
    complete: bool
    missing_days: list[str]
    message: str | None
    pending: bool = False


class HistoryStatus(BaseModel):
    complete: bool
    expected_days: int
    published_days: int
    missing_days: list[str]
    start_date: str | None
    unit: Literal["stock", "trading_day"] = "trading_day"


class RunStatus(BaseModel):
    state: str
    started_at: str
    ended_at: str | None
    progress: str
    error: str | None
    warnings: list[str]


class DataStatus(BaseModel):
    available: bool
    trade_date: str | None
    expected_date: str | None
    stale: bool
    stock_count: int
    unclassified_count: int
    source: str
    industry_source: str
    industry_synced_at: str | None = None
    industry_source_updated_at: str | None = None
    industry_l2_available: bool = False
    industry_l2_count: int = 0
    industry_l2_unclassified_count: int = 0
    industry_stale: bool = True
    missing_quote_count: int = 0
    missing_cap_count: int = 0
    history: HistoryStatus
    last_run: RunStatus | None
