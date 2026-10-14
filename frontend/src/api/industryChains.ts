import { get, type Stock } from "./index";
export interface Evidence {
  source_id: string;
  locator: string;
  summary: string;
}
export interface ChainSource {
  id: string;
  title: string;
  url: string;
  published_on: string | null;
  retrieved_on: string;
  report_period: string | null;
  access_status: string;
  category?: "primary" | "vendor" | "framework";
  snapshot_hash?: string;
}
export interface Analysis {
  id: string;
  trigger: string;
  target: string;
  direction: string;
  mechanism: string;
  conditions: string;
  horizon: string;
  indicators: string[];
  kind: string;
  evidence: Evidence[];
}
export interface ChainNode {
  assertion_kind?: string;
  key: string;
  name: string;
  stage: string;
  description: string;
  variable: string;
  main: boolean;
  column: number;
  order: number;
  competition: string;
  gap: string;
  evidence: Evidence[];
  analyses: Analysis[];
  stock_count: number;
  leader_count: number;
}
export interface ChainEdge {
  assertion_kind?: string;
  key: string;
  source: string;
  target: string;
  kind: string;
  description: string;
  conditions: string;
  evidence: Evidence[];
}
export interface Metric {
  period: string;
  disclosed_on: string | null;
  verification?: string;
  subject: string;
  basis: string;
  currency: string;
  revenue: number | null;
  share: number | null;
  missing_reason: string;
  evidence: Evidence[];
}
export interface Leader {
  freshness?: string;
  kind: string;
  product: string;
  geography: string;
  period: string;
  reason: string;
  evidence: Evidence[];
}
export interface Membership {
  company_analysis?: string[];
  mapping_status?: string;
  financial_status?: string;
  key: string;
  node: string;
  subject: string;
  business: string;
  participation: string;
  operating_stage: string;
  evidence: Evidence[];
  metrics: Metric[];
  leaders: Leader[];
}
export interface ChainStock extends Stock {
  memberships: Membership[];
  nodes: { key: string; name: string }[];
  comparison_metrics?: Metric[];
}
export interface ChainMeta {
  chain_id: string;
  revision_id: string;
  current_revision_id: string;
  content_as_of: string;
  reviewed_at: string;
  review_note: string;
  reviewer: string;
  published_at: string;
  review_status: string;
}
export interface ChainCard extends ChainMeta {
  coverage_level: "baseline" | "curated";
  analysis_version: number;
  industry_level: number | null;
  industry_ids: string[];
  parent_industry_id: string | null;
  verified_count: number;
  recommendation_reason?: string;
  match_reason?: string;
  id: string;
  name: string;
  scope: string;
  summary: string;
  node_count: number;
  stock_count: number;
  leader_count: number;
}
export interface ChainDetail extends ChainCard {
  aliases: string[];
  demand: string;
  focus: string[];
  gaps: string[];
  nodes: ChainNode[];
  edges: ChainEdge[];
  sources: ChainSource[];
  change_note: string;
}
export interface ChainStocks extends ChainMeta {
  items: ChainStock[];
  total: number;
  page: number;
  page_size: number;
  registered_count: number;
  unmatched_count: number;
  filtered_count: number;
  stock_count: number;
}
export interface ChainComparison extends ChainMeta {
  node_key: string;
  items: ChainStock[];
  invalid_items: { id: number; reason: string }[];
  period: string | null;
  common_periods: string[];
  comparable: boolean;
  reason: string;
}
export function chainGet<T>(
  path = "",
  params: Record<string, unknown> = {},
  signal?: AbortSignal,
) {
  const query = new URLSearchParams();
  for (const [k, v] of Object.entries(params))
    if (v !== null && v !== undefined && v !== "") query.set(k, String(v));
  return get<T>(
    "/industry-chains" + path + (query.size ? "?" + query : ""),
    signal,
  );
}

export interface IndustryCoverage {
  id: string;
  name: string;
  level: number;
  parent_id: string | null;
  company_count: number;
  analysis_ready: boolean;
  business_count: number;
  financial_count: number;
  status: string;
  chains: { id: string; name: string; coverage_level: string }[];
}
export interface Coverage {
  items: IndustryCoverage[];
  total: number;
  l1_count: number;
  l2_count: number;
  covered_count: number;
  analysed_count: number;
  company_count: number;
  business_count: number;
  financial_count: number;
  collection: {
    collected_at: string;
    periods: string[];
    missing_financials: string[];
  } | null;
}
export interface ChainCatalog {
  items: ChainCard[];
  total: number;
  page: number;
  page_size: number;
  coverage: Coverage;
  recommendations: ChainCard[];
}

export interface ChainUpdateStatus {
  enabled: boolean;
  interval_hours: number;
  state: string;
  phase: string | null;
  last_success_at: string | null;
  next_check_at: string | null;
  error: string | null;
  logic_reviewed_on: string;
  logic_review_due_on: string;
  logic_review_overdue: boolean;
  maintenance: {
    leader_review_count: number;
    source_review_count: number;
    evidence_checked_at: string;
  } | null;
}
