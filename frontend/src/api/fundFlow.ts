export type FundPeriod = "today" | "5d" | "10d";
export type FundKind = "concept" | "industry";
export type FundSort =
  "net_desc" | "net_asc" | "rate_desc" | "rate_asc" | "pct_desc" | "pct_asc";
export interface FundMeta {
  source: string;
  classification_source: string;
  period: string;
  trade_date: string | null;
  source_as_of: string | null;
  fetched_at: string | null;
  batch_id: string | null;
  window_note: string | null;
  pending: boolean;
  stale: boolean;
  error: string | null;
  retry_at: string | null;
  quality_status: string;
  missing_count: number;
  valid_count: number;
  auto_update: boolean;
}
export interface FundRow {
  code: string;
  name: string;
  net_amount: number | null;
  net_rate: number | null;
  pct_change: number | null;
  extra_large: number | null;
  large: number | null;
  medium: number | null;
  small: number | null;
  lead_stock: string | null;
  trade_date: string | null;
  source_as_of: string | null;
}
export interface FundBoard extends FundRow {
  id: string;
  kind: FundKind;
  rank: number;
}
export type FundChartBoard = Omit<FundBoard, "rank">;
export interface FundRanking {
  items: FundBoard[];
  total: number;
  page: number;
  page_size: number;
  meta: FundMeta;
  overview: {
    valid_count: number;
    total_count: number;
    top_in: FundBoard | null;
    top_out: FundBoard | null;
  };
  chart: { inflows: FundChartBoard[]; outflows: FundChartBoard[] };
}
export interface FundDetail {
  board: {
    id: string;
    kind: FundKind;
    code: string;
    name: string;
    source: string;
  };
  summary: FundRow | null;
  breakdown: FundRow | null;
  meta: FundMeta;
  breakdown_meta: FundMeta;
  lead_stock_id: number | null;
  lead_unavailable_reason: string | null;
}
export interface FundDay {
  trade_date: string;
  net_amount: number | null;
  net_rate: number | null;
  provisional: boolean;
  gap?: boolean;
}
export interface FundHistory {
  items: FundDay[];
  available_days: number;
  available_start: string | null;
  available_end: string | null;
  meta: FundMeta;
}
export interface FundStock extends FundRow {
  stock_id: number;
  price: number | null;
  ts_code: string;
}
export interface FundStocks {
  items: FundStock[];
  total: number;
  page: number;
  source_count: number;
  filtered_count: number;
  unmatched_count: number;
  missing_count: number;
  meta: FundMeta;
}
export const periodLabels: Record<FundPeriod, string> = {
  today: "今日",
  "5d": "5日",
  "10d": "10日",
};
