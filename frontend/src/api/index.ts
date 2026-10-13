import type { Exchange } from "../marketOptions";

export interface Representative {
  reason: string;
  source_url: string;
  reviewed_at: string;
  weight_date: string | null;
  industry_level: 1 | 2;
}
export interface Stock {
  profile_pending: boolean;
  id: number;
  code: string;
  ts_code: string;
  name: string;
  industry_id: string;
  industry: string;
  industry_l2_id: string | null;
  industry_l2: string | null;
  board: string;
  exchange: string;
  list_date: string;
  fullname: string | null;
  introduction: string | null;
  main_business: string | null;
  updated_at: string;
  close: number | null;
  pct_chg: number | null;
  amount: number | null;
  market_cap: number | null;
  float_market_cap: number | null;
  turnover_rate: number | null;
  pe_ratio: number | null;
  pe_basis: string | null;
  pb_ratio: number | null;
  total_shares: number | null;
  float_shares: number | null;
  quote_date: string | null;
  status: string;
  is_st: boolean;
  st_source: string;
  representative: Representative | null;
}
export interface Industry {
  id: string;
  name: string;
  level: 1 | 2;
  parent_id: string | null;
  parent_name: string | null;
  stock_count: number;
  representative_count: number;
}
export interface Concept {
  id: string;
  name: string;
  stock_count: number;
  source: string;
  fetched_at: string | null;
  error: string | null;
}
export interface Group {
  id: string;
  name: string;
  stock_count: number;
  items: Stock[];
}
export interface StockResult {
  navigation?: {
    previous_id: number | null;
    next_id: number | null;
    position: number;
    total: number;
  };
  items: Stock[];
  groups: Group[];
  total: number;
  matched_stocks: number;
  pagination_unit: "stock" | "industry";
  page: number;
  page_size: number;
  trade_date: string | null;
}
export interface DataStatus {
  available: boolean;
  trade_date: string | null;
  expected_date: string | null;
  stale: boolean;
  stock_count: number;
  unclassified_count: number;
  source: string;
  industry_source: string;
  industry_synced_at: string | null;
  industry_source_updated_at: string | null;
  industry_l2_available: boolean;
  industry_l2_count: number;
  industry_l2_unclassified_count: number;
  industry_stale: boolean;
  missing_quote_count: number;
  missing_cap_count: number;
  history: {
    complete: boolean;
    expected_days: number;
    published_days: number;
    missing_days: string[];
    start_date: string | null;
    unit: "stock" | "trading_day";
  };
  last_run: null | {
    state: string;
    progress: string;
    error: string | null;
    warnings: string[];
    started_at: string;
    ended_at: string | null;
  };
}
export interface Prices {
  pending: boolean;
  start_date: string | null;
  stale: boolean;
  points: {
    status: "trading" | "suspended" | "missing";
    date: string;
    open: number | null;
    high: number | null;
    low: number | null;
    close: number | null;
    volume: number | null;
  }[];
  basis_date: string | null;
  adjustment: string;
  complete: boolean;
  missing_days: string[];
  message: string | null;
}
export interface Filters {
  view: "industry" | "concept";
  keyword: string;
  industry_id: string;
  concept_id: string;
  industry_level: 1 | 2;
  exchange: Exchange;
  board: string;
  scope: "all" | "representatives";
  collection: "all" | "favorites";
  sort:
    | "default"
    | "pct_desc"
    | "pct_asc"
    | "market_cap_desc"
    | "market_cap_asc"
    | "close_asc"
    | "close_desc"
    | "amount_asc"
    | "amount_desc"
    | "turnover_asc"
    | "turnover_desc";
  page: number;
  page_size: number;
}
export async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch("/api" + path, { signal });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "请求失败" }));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : `查询参数有误（${response.status}）`,
    );
  }
  return response.json();
}
