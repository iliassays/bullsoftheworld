import { currentLang } from "./i18n";
import { analyticsAllowed } from "./consent";

// Minimal typed API client. The short-lived access token is injected from memory.
// Use 127.0.0.1 (not "localhost") so the browser doesn't try IPv6 ::1 first,
// which the API doesn't bind. Override with VITE_API_BASE if needed.
const BASE =
  (import.meta.env.VITE_API_BASE as string) || "http://127.0.0.1:8090";

// Direct URL for a company logo image (served by the API; 404s when we have none → UI falls back).
export const logoUrl = (code: string) => `${BASE}/symbols/${encodeURIComponent(code)}/logo`;
const LEGACY_TOKEN_KEY = "bulls.token";

function tenantHost(): string | undefined {
  return typeof window === "undefined" ? undefined : window.location.hostname;
}

function tenantHeaders(): Record<string, string> {
  const host = tenantHost();
  return host ? { "X-Tenant-Host": host } : {};
}

let accessToken: string | null = null;
export const tokenStore = {
  get: () => accessToken,
  set: (token: string) => {
    accessToken = token;
    localStorage.removeItem(LEGACY_TOKEN_KEY);
  },
  clear: () => {
    accessToken = null;
    localStorage.removeItem(LEGACY_TOKEN_KEY);
  },
};

function tenantStorageKey(name: string): string {
  const host = tenantHost()?.toLowerCase() || "local";
  return `bulls.${host}.${name}`;
}

// Local development can receive a body refresh token; production uses the tenant-specific
// HttpOnly cookie. Namespace the fallback anyway so one host can never reuse another login.
const REFRESH_KEY = tenantStorageKey("refresh");
export const refreshStore = {
  get: () => localStorage.getItem(REFRESH_KEY),
  set: (t: string) => localStorage.setItem(REFRESH_KEY, t),
  clear: () => localStorage.removeItem(REFRESH_KEY),
};


// Stable anonymous client id so page views can be de-duped without a login.
const CID_KEY = tenantStorageKey("cid");
function clientId(): string {
  let id = localStorage.getItem(CID_KEY);
  if (!id) {
    id =
      crypto?.randomUUID?.() ??
      `c_${Math.random().toString(36).slice(2)}${Date.now()}`;
    localStorage.setItem(CID_KEY, id);
  }
  return id;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
  }
}

// Single-flight refresh: many parallel 401s must trigger ONE rotation, not a stampede
// (a second rotation of the same token trips the reuse detector and kills the session).
let refreshing: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  refreshing ??= (async () => {
    const rt = refreshStore.get();
    try {
      const res = await fetch(`${BASE}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...tenantHeaders() },
        credentials: "include",
        body: JSON.stringify(rt ? { refresh_token: rt } : {}),
      });
      if (!res.ok) throw new Error();
      const body = await res.json();
      tokenStore.set(body.access_token);
      if (body.refresh_token) refreshStore.set(body.refresh_token);
      else refreshStore.clear();
      return true;
    } catch {
      // Rotation failed → the session is genuinely dead; clear so the UI shows logged-out.
      tokenStore.clear();
      refreshStore.clear();
      return false;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

async function request<T>(path: string, opts: RequestInit = {}, retried = false): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-Locale": currentLang(),
    ...tenantHeaders(),
    ...(opts.headers as Record<string, string>),
  };
  const token = tokenStore.get();
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, { ...opts, headers, credentials: "include" });
  // Access token expired mid-session → rotate the refresh token once and replay the call.
  // /auth/* is excluded so a failing login/refresh can never recurse.
  if (res.status === 401 && !retried && !path.startsWith("/auth/")) {
    if (await tryRefresh()) return request<T>(path, opts, true);
  }
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => ({}));
  if (!res.ok)
    throw new ApiError(res.status, errorMessage(body?.detail, res.statusText));
  return body as T;
}

// FastAPI returns `detail` as a string (HTTPException) OR an array of validation objects (422).
// Always reduce it to a readable string so the UI never tries to render an object (React #31).
function errorMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    const o = detail as { reason?: string; error?: string; categories?: string[] };
    if (o.reason) return o.reason.replace(/_/g, " ");
    if (o.error) return o.error;
  }
  if (Array.isArray(detail)) {
    const parts = detail.map((d) => {
      const o = (d ?? {}) as { loc?: unknown[]; msg?: string; type?: string };
      const field =
        Array.isArray(o.loc) && o.loc.length
          ? String(o.loc[o.loc.length - 1])
          : "";
      // Hide the raw regex from users; keep the readable length/required messages.
      const msg =
        o.type === "string_pattern_mismatch" ? "invalid format" : (o.msg ?? "");
      return field && msg ? `${field}: ${msg}` : msg;
    });
    return parts.filter(Boolean).join("; ") || fallback;
  }
  return fallback;
}

// --- types (mirror the API schemas) ---
export interface Quote {
  market: string;
  code: string;
  ltp: number;
  change: number;
  change_pct: number;
  open: number | null;
  high: number;
  low: number;
  close: number;
  prev_close: number | null;
  volume: number;
  trades: number;
  as_of: string;
  is_delayed: boolean;
}
export interface SymbolOut {
  market: string;
  code: string;
  name_en: string;
  name_bn: string | null;
  sector: string | null;
  category: string | null;
  is_active: boolean;
  data_status: "reference_only" | "onboarding" | "ready" | "research_only" | "degraded";
}
export interface SymbolDetail {
  symbol: SymbolOut;
  quote: Quote | null;
  research_limitations: string[];
}
export interface ResearchPreparation {
  code: string;
  status: "queued" | "running" | "review_required" | "ready" | "research_only" | "rejected" | "failed" | "reference_only" | "onboarding" | "degraded";
  symbol_status: SymbolOut["data_status"];
  run_id: string | null;
  attempts: number;
  request_count: number;
  requested_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  failure_reasons: string[];
  can_open: boolean;
  disclosure: string;
}
export interface Bar {
  date: string; // YYYY-MM-DD
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}
export interface Digest {
  code: string;
  summary: string;
  mood: "bullish" | "bearish" | "mixed" | "quiet";
  posts: number;
  change_pct_1d: number;
}
export interface ResearchSource {
  type: string;
  id: string;
  title: string;
  date: string | null;
  snippet: string;
  reliability: "official" | "market" | "system" | "crowd";
  url?: string | null;
}
export interface ResearchInsight {
  lens: "valuation" | "technical" | "liquidity" | "ownership" | "disclosure" | "crowd";
  stance: "constructive" | "watch" | "risk" | "unknown";
  title: string;
  detail: string;
  evidence: string;
}
export interface ResearchBrief {
  code: string;
  question: string;
  answer: string;
  evidence_quality: "strong" | "mixed" | "weak";
  official_catalyst: boolean;
  blocked_advice: boolean;
  as_of: string;
  facts: string[];
  insights: ResearchInsight[];
  sources: ResearchSource[];
}
export interface Level {
  value: number;
  date: string;
}
// A detected chart pattern. These are descriptive watchlist structures, not trade instructions;
// the flat-base study improved selectivity but did not show stable standalone return edge.
export interface PricePoint {
  date: string;
  price: number;
}
export interface PatternPoint extends PricePoint {
  kind: "high" | "low";
}
export interface LineSeg {
  start: PricePoint;
  end: PricePoint;
}
export type PatternType =
  | "double_top"
  | "double_bottom"
  | "ascending_triangle"
  | "descending_triangle"
  | "channel_up"
  | "channel_down"
  | "channel_horizontal"
  | "high_volume_flat_base";
export type PatternStatus =
  | "forming"
  | "confirmed_breakout_up"
  | "confirmed_breakout_down"
  | "invalidated";
export interface PatternMatch {
  pattern_type: PatternType;
  status: PatternStatus;
  start_date: string;
  end_date: string;
  breakout_date: string | null;
  pivots: PatternPoint[];
  resistance_line: LineSeg | null;
  support_line: LineSeg | null;
  key_levels: number[];
  strength_score: number;
  touches_resistance: number;
  touches_support: number;
  metrics: Record<string, number>;
}
// Deterministic technical-analysis snapshot — descriptive facts only, never a recommendation.
export interface Analytics {
  market: string;
  code: string;
  as_of_date: string;
  bars_used: number;
  last_close: number;
  sma_20: number | null;
  sma_50: number | null;
  sma_200: number | null;
  ema_20: number | null;
  above_sma_50: boolean | null;
  above_sma_200: boolean | null;
  rsi_14: number | null;
  atr_14: number | null;
  recent_swing_high: Level | null;
  recent_swing_low: Level | null;
  nearest_support: number | null;
  nearest_resistance: number | null;
  week52_high: number | null;
  week52_low: number | null;
  pct_from_52w_high: number | null;
  pct_from_52w_low: number | null;
  last_volume: number;
  avg_volume_20: number | null;
  relative_volume: number | null;
  patterns: PatternMatch[];
}
export interface WatchItem {
  code: string;
  change_pct: number;
  posts: number;
  bull: number;
  bear: number;
}
export interface Breadth {
  advancers: number;
  decliners: number;
  unchanged: number;
  total: number;
}
export type MarketSession = "pre_open" | "open" | "post_close" | "weekend";
export interface TodaysWatch {
  summary: string;
  items: WatchItem[];
  breadth: Breadth | null;
  session: MarketSession;
  research?: Array<{
    board_key: string;
    board_title: string;
    code: string;
    change_1d: number | null;
    reason: string;
  }>;
  personal?: Array<{ kind: string; code: string | null; title: string }>;
}
export interface MomHorizons {
  m3: number | null;
  m6: number | null;
  m12: number | null;
}
export interface ScreenItem {
  code: string;
  name: string;
  last_close: number;
  value: number;
  change_1d: number | null; // today's % move; null for movers (their value is already a change)
  note: string | null; // optional per-row qualifier (momentum: steady / volatile / possible pump)
  spark: number[]; // recent closes (oldest→newest) for an inline sparkline
  horizons?: MomHorizons | null; // momentum screen only: 3M/6M/12M returns for the consistency cue
  flow?: number[]; // ownership screens: stake % over last disclosures (oldest→newest)
  flow_dates?: string[]; // ISO date of each flow point, aligned with `flow`
  comparison_as_of?: string | null; // prior ownership/13F report date for this change
  data_as_of?: string | null; // latest ownership/13F report date for this change
  public_as_of?: string | null; // filing/publication date when distinct from the report period
  period_spark?: number[]; // ownership: price over the disclosure window (oldest→newest)
  category?: string | null;
  adtv_mn?: number | null;
  turnover_mn?: number | null;
  safe_order_mn?: number | null;
  market_cap_mn?: number | null;
  cap_tier?: "mega" | "large" | "mid" | "small" | "micro" | null; // null/absent = unclassified
  free_float_cap_mn?: number | null;
  liquidity?: string | null;
  setup_quality?: string | null;
  why?: string | null;
  catalyst?: string | null;
  catalyst_date?: string | null;
  catalyst_category?: string | null;
  scanner_label?: string | null;
  how_to_read?: string | null;
  risk_note?: string | null;
  check_next?: string[];
  pattern_status?: PatternStatus | null;
  pattern_metrics?: Record<string, number> | null;
  new_since?: string | null; // entered this tenant/market/size board within the API's recent window
  new_reason?: "board_entry" | "new_disclosure" | null;
}
export interface Screen {
  key: string;
  title: string;
  description: string;
  value_label: string;
  group: string;
  evidence?: "backtested" | "experimental" | "framework" | "utility" | null;
  total_count?: number | null;
  items: ScreenItem[];
}
export interface MarketMethodology {
  market: string;
  settlement_cycle: string;
  data_clock: string;
  liquidity_floor: string;
  min_adtv_mn: number;
  min_mcap_mn: number;
  min_free_float_cap_mn: number;
}
export interface ScannerResponse {
  as_of: string | null;
  quote_as_of: string | null;
  tab: string;
  strategy_pack: string;
  cap_tier?: string | null;
  tabs: Array<{ key: string; title: string; description: string }>;
  market_regime?: "above_200dma" | "below_200dma" | null;
  boards: Screen[];
}
// A localisable statement about a row: the server sends `kind` (+ at most one number) and the
// client renders it, so a Bangla reader gets Bangla evidence rather than English prose.
export interface ShortlistFact {
  kind: string;
  value?: number | null;
}
export interface ShortlistHorizonOutcome {
  sessions: number;
  close_return_pct?: number | null;
  as_of?: string | null;
}
export interface DailyShortlistRow {
  code: string;
  name_en?: string | null;
  name_bn?: string | null;
  rank: number;
  attention_score: number;
  close: number;
  change_pct?: number | null;
  sector?: string | null;
  pe?: number | null;
  facts: ShortlistFact[];
  cautions: ShortlistFact[];
  // English renderings of the same facts — the fallback when a `kind` has no local string yet.
  reasons: string[];
  unknowns: string[];
  return_since_pct?: number | null;
  max_went_pct?: number | null;
  min_went_pct?: number | null;
  latest_close?: number | null;
  sessions_since: number;
  outcome_as_of?: string | null;
  horizon_returns: ShortlistHorizonOutcome[];
  appearance_number?: number | null;
  first_recorded_appearance_date?: string | null;
}
export interface DailyShortlist {
  market: string;
  as_of: string;
  available_dates: string[];
  latest_date?: string | null;
  evidence_mode: "forward" | "reconstructed" | "live";
  quote_as_of?: string | null;
  is_delayed: boolean;
  size: number;
  rows: DailyShortlistRow[];
  eligible_names: number;
  excluded_illiquid: number;
  excluded_short_history: number;
  // Always false from the server. The slate ranks where to LOOK, never expected return —
  // measured: a return-seeking rank did 1.24pp worse than a random draw from the same pool.
  is_return_claim: boolean;
  methodology_version: string;
  base_rates: Record<string, unknown>;
  notes: string[];
  source: "bulls_daily_shortlist_eod";
}
export interface ShortlistHorizonPerformance {
  sessions: number;
  matured_appearances: number;
  observations: number;
  benchmark_observations: number;
  pending_appearances: number;
  missing_bar_appearances: number;
  suspicious_price_paths: number;
  coverage_pct?: number | null;
  mean_return_pct?: number | null;
  median_return_pct?: number | null;
  positive_rate_pct?: number | null;
  mean_benchmark_return_pct?: number | null;
  mean_excess_return_pct?: number | null;
  median_excess_return_pct?: number | null;
  excess_ci_low_pct?: number | null;
  excess_ci_high_pct?: number | null;
  next_open_observations: number;
  limit_locked_entries: number;
  next_open_mean_return_pct?: number | null;
  next_open_median_return_pct?: number | null;
  next_open_positive_rate_pct?: number | null;
}
export interface ShortlistPerformanceCohort {
  key: "independent_episodes" | "all_appearances" | "forward_only";
  appearances: number;
  selection_sessions: number;
  first_selection_date?: string | null;
  last_selection_date?: string | null;
  horizons: ShortlistHorizonPerformance[];
}
export interface ShortlistArchiveIntegrity {
  rows: number;
  sessions: number;
  matched_selection_closes: number;
  missing_selection_bars: number;
  close_mismatches: number;
  matched_selection_moves: number;
  missing_move_inputs: number;
  move_mismatches: number;
  incomplete_sessions: number;
  invalid_rank_sessions: number;
  methodology_versions: string[];
}
export interface DailyShortlistPerformance {
  market: string;
  as_of?: string | null;
  all_appearances: number;
  forward_appearances: number;
  reconstructed_appearances: number;
  independent_episodes: number;
  cohorts: ShortlistPerformanceCohort[];
  integrity: ShortlistArchiveIntegrity;
  edge_status:
    | "insufficient_history"
    | "no_observed_excess"
    | "positive_but_unproven"
    | "positive_diagnostic_requires_forward_validation";
  primary_horizon_sessions: number;
  caveats: string[];
  source: "daily_shortlist_archive_and_dse_eod";
}
export interface ScreensResponse {
  as_of: string | null; // EOD analytics date — screen rankings are as-of this close
  quote_as_of?: string | null; // latest 15-min quote snapshot — price/"today's move" freshness
  methodology?: MarketMethodology;
  cap_tier?: string | null;
  screens: Screen[];
}
export interface Sector {
  sector: string;
  avg_change: number;
  advancers: number;
  decliners: number;
  count: number;
}
export interface MarketPulse {
  as_of: string | null;
  quote_as_of?: string | null;
  close_as_of?: string | null;
  data_status: "intraday_delayed" | "provisional_close" | "official_close" | "stale";
  refresh_interval_minutes: number;
  benchmark_is_live: boolean;
  turnover_is_partial: boolean;
  turnover_is_estimated: boolean;
  dsex: number | null;
  dsex_change_pct: number | null;
  turnover_cr: number | null;
  benchmark_label?: string | null;
  benchmark_close?: number | null;
  benchmark_change_pct?: number | null;
  turnover_mn?: number | null;
  turnover_vs_20d: number | null;
  advancers: number;
  decliners: number;
  unchanged: number;
  total: number;
  published_symbols: number;
  eligible_symbols: number;
  coverage_ratio: number;
  coverage_complete: boolean;
  top_sector: string | null;
  top_sector_change: number | null;
  weak_sector: string | null;
  weak_sector_change: number | null;
  risk_mode: "risk_on" | "mixed" | "defensive";
}
export interface Buzz {
  code: string;
  watchers: number;
  watchers_delta_7d: number | null;
  posts_24h: number;
  posts_baseline: number | null;
  chatter_x: number | null;
  attention: "rising" | "normal" | "quiet" | null;
  reactions_24h: number;
  replies_24h: number;
}
export interface BrowseSizeItem {
  code: string;
  name_en: string;
  name_bn: string | null;
  sector: string | null;
  last_close: number | null;
  change_pct: number | null;
  market_cap_mn: number | null;
  cap_tier: string | null; // null = unclassified
}
export interface BrowseSize {
  market: string;
  tier: string;
  tiers: string[]; // market's tier vocabulary, largest first
  as_of: string | null; // analytics freshness — always show it
  counts: { tier: string; count: number }[];
  total: number;
  items: BrowseSizeItem[];
}
export interface Company {
  code: string;
  fundamentals: {
    valuation_as_of: string | null;
    market_cap_mn: number | null;
    cap_tier: "mega" | "large" | "mid" | "small" | "micro" | null;
    pe_ratio: number | null;
    pb_ratio: number | null;
    dividend_yield: number | null;
    pe_vs_sector: number | null;
    eps: number | null;
    nav_per_share: number | null;
    eps_growth_yoy: number | null;
    outstanding_shares: number | null;
    free_float_cap_mn: number | null;
    face_value: number | null;
    sector: string | null;
    credit_rating: string | null;
    week52_high: number | null;
    week52_low: number | null;
    avg_volume_20: number | null;
  };
  ownership: {
    sponsor_pct: number | null;
    govt_pct: number | null;
    institute_pct: number | null;
    foreign_pct: number | null;
    public_pct: number | null;
    sponsor_delta: number | null;
    govt_delta: number | null;
    institute_delta: number | null;
    foreign_delta: number | null;
    public_delta: number | null;
    composition_total: number | null;
    as_of: string | null;
    history: {
      as_of: string;
      sponsor: number | null;
      govt: number | null;
      institute: number | null;
      foreign: number | null;
      public: number | null;
    }[];
  };
  earnings: {
    fiscal_year: number;
    eps: number | null;
    nav_per_share: number | null;
    profit_mn: number | null;
  }[];
  dividends: {
    year: number;
    cash_pct: number | null;
    cash_per_share: number | null;
    bonus_pct: number | null;
  }[];
  quarters: {
    period_end: string;
    revenue_mn: number | null;
    net_income_mn: number | null;
    eps: number | null;
    source_url: string | null;
  }[];
  financial_health: {
    as_of: string | null;
    revenue_ttm_mn: number | null;
    net_income_ttm_mn: number | null;
    profit_margin_pct: number | null;
    operating_cash_flow_ttm_mn: number | null;
    capital_expenditure_ttm_mn: number | null;
    free_cash_flow_ttm_mn: number | null;
    assets_mn: number | null;
    liabilities_mn: number | null;
    equity_mn: number | null;
    cash_mn: number | null;
    debt_mn: number | null;
    current_ratio: number | null;
    debt_to_equity: number | null;
    source_url: string | null;
  };
}
export interface NewsDetails {
  // earnings
  eps_current?: number;
  eps_prior?: number;
  eps_trend?: "up" | "down" | "flat" | "loss_widened" | "loss_narrowed" | "to_loss" | "to_profit";
  nav?: number;
  nocfps?: number;
  period?: "Q1" | "H1" | "Q3" | "annual";
  // dividend
  cash_pct?: number;
  stock_pct?: number;
  no_dividend?: boolean;
  per_share_cash?: number;
  face_value?: number;
  year_ended?: string;
  agm_date?: string;
  // board meeting
  meeting_date?: string;
  agenda?: ("financials" | "dividend")[];
  // corporate action / halt
  record_date?: string;
  spot_from?: string;
  spot_to?: string;
  // rating
  long_term?: string;
  short_term?: string;
  outlook?: string;
  action?: "upgrade" | "downgrade";
  source?: string;
  form?: string;
  report_date?: string;
  items?: string;
  accession_number?: string;
}
export interface NewsItem {
  published_at: string;
  category: string;
  strength: number;
  headline: string;
  details?: NewsDetails | null;
  url?: string | null;
}

export interface InstitutionalPosition {
  manager_cik: number;
  manager_name: string;
  shares: number;
  value_usd: number;
  prior_shares: number | null;
  share_change: number | null;
  change_pct: number | null;
  change_type: "new" | "increased" | "reduced" | "unchanged" | "exited";
  filing_date: string;
  url: string;
}

export interface InstitutionalActivity {
  code: string;
  periods: Array<{
    report_date: string;
    prior_report_date: string | null;
    public_by: string;
    managers_count: number;
    total_shares: number;
    total_value_usd: number;
    net_share_change: number | null;
    net_change_pct: number | null;
    new_positions: number;
    increased_positions: number;
    reduced_positions: number;
    exited_positions: number;
    unchanged_positions: number;
    close_on_public_date: number | null;
    latest_close: number | null;
    return_since_public_pct: number | null;
    return_30_sessions_pct: number | null;
    return_60_sessions_pct: number | null;
    benchmark_return_30_sessions_pct: number | null;
    benchmark_return_60_sessions_pct: number | null;
    excess_return_30_sessions_pct: number | null;
    excess_return_60_sessions_pct: number | null;
    adding_managers: number;
    reducing_managers: number;
    net_breadth_pct: number | null;
    source_url: string;
  }>;
  horizons: Array<{
    quarters: number;
    from_report_date: string;
    to_report_date: string;
    reported_share_change_pct: number;
  }>;
  manager_histories: Array<{
    manager_cik: number;
    manager_name: string;
    latest_value_usd: number;
    manager_style: string | null;
    interpretation: string | null;
    points: Array<{
      report_date: string;
      reported_manager_name: string;
      shares: number;
      value_usd: number;
      share_change: number | null;
      change_pct: number | null;
      change_type: "new" | "increased" | "reduced" | "unchanged" | "exited";
      filing_date: string;
      url: string;
    }>;
  }>;
  top_positions: InstitutionalPosition[];
  top_new: InstitutionalPosition[];
  top_increases: InstitutionalPosition[];
  top_reductions: InstitutionalPosition[];
  top_exits: InstitutionalPosition[];
  history_quarters: number;
  target_history_quarters: number;
  history_status: "not_available" | "building_history" | "full_history";
  identifier_count: number;
  mapping_confidence: number | null;
  mapping_methods: string[];
  bounded_manager_history: boolean;
  disclosure_note: string;
  limitations: string[];
}
export interface ShortVolumeActivity {
  code: string;
  as_of_date: string | null;
  status: "not_available" | "limited_history" | "elevated" | "below_normal" | "normal";
  status_label: string;
  short_share_pct: number | null;
  average_20_pct: number | null;
  deviation_pp: number | null;
  percentile_60: number | null;
  z_score: number | null;
  activity_vs_20x: number | null;
  baseline_sessions: number;
  points: Array<{
    date: string;
    short_share_pct: number;
    short_exempt_share_pct: number;
    finra_reported_volume: number;
  }>;
  source_url: string | null;
  interpretation: string;
  limitations: string[];
}
export interface TrendingReason {
  kind: "volume" | "turnover" | "near_high" | "near_low" | "move" | "limit_up" | "limit_down";
  mult?: number;
  cr?: number;
  pct?: number;
}
export interface EarningsEvent {
  code: string;
  name_en: string;
  name_bn?: string | null;
  category?: string | null;
  meeting_date: string;
  period?: "Q1" | "H1" | "Q3" | "annual" | null;
  status?: "confirmed" | "estimated";
  source?: string | null;
  url?: string | null;
  day_total?: number | null;
}
export interface TrendingStock {
  code: string;
  name_en: string;
  name_bn: string | null;
  ltp: number | null;
  change_pct: number;
  direction: "up" | "down" | "flat";
  heating_up: boolean;
  reasons: TrendingReason[];
  category?: string | null;
  adtv_mn?: number | null;
  safe_order_mn?: number | null;
  turnover_mn?: number | null;
  liquidity?: string | null;
}
export interface ReadPoint {
  tag: string;
  text: string;
}
export interface PlainRead {
  code: string;
  as_of_date: string;
  headline: string;
  points: ReadPoint[];
  how_to_read: string;
  disclaimer: string;
}
export interface Gauge {
  score: number;
  label: string;
}
export interface Pulse {
  code: string;
  sentiment: Gauge;
  message_volume: Gauge;
  participation: Gauge;
}
export interface MarketStatus {
  phase: "open" | "pre_open" | "post_close" | "weekend";
  as_of: string | null;
  market_time: string;
  expected_analysis_date: string;
  next_analysis_at: string;
  quote_is_stale: boolean;
}
export interface MarketConfig {
  market: string;
  exchange_code: string;
  exchange_label_bn: string | null;
  exchange_name: string;
  exchange_name_bn: string | null;
  country_code: string;
  currency_code: string;
  currency_symbol: string;
  timezone: string;
  timezone_label: string;
  place_label_en: string;
  place_label_bn: string;
  open_time: string;
  close_time: string;
  settlement_cycle: string;
  benchmark_label: string;
  default_locale: string;
  supported_locales: string[];
  price_alert_evaluation: "delayed_quote" | "session_close";
  price_decimals: number;
  compact_money_units: Array<{
    min_value_mn: number;
    divisor_mn: number;
    suffix: string;
    decimals: number;
  }>;
  market_cap_money_units: Array<{
    min_value_mn: number;
    divisor_mn: number;
    suffix: string;
    decimals: number;
  }>;
  cap_tiers: Array<"mega" | "large" | "mid" | "small" | "micro">;
  features: Record<string, boolean>;
  tenant_name: string;
  brand_name: string;
  site_url: string;
  support_email: string;
  logo_url: string;
  tagline_en: string;
  tagline_bn: string;
  research_beta: boolean;
  social_url: string | null;
}
export interface MoodComponent {
  key: string;
  label: string;
  score: number;
  detail: string;
}
export interface MoodIndex {
  as_of_date: string;
  as_of: string | null;
  data_status: "intraday_delayed" | "provisional_close" | "official_close" | "stale";
  close_as_of_date: string | null;
  refresh_interval_minutes: number | null;
  score: number | null;
  band:
    | "extreme_fear"
    | "fear"
    | "neutral"
    | "greed"
    | "extreme_greed"
    | "unknown";
  label: string;
  components: MoodComponent[];
  context: string[];
  caption: string;
  disclaimer: string;
}
export interface ScorecardDimension {
  key: string;
  label: string;
  score: number;
  detail: string;
  assessment: string;
  benchmark: string;
}
export interface RedFlag {
  key: string;
  label: string;
}
export interface ScorecardResponse {
  scorecard: {
    code: string;
    as_of_date: string;
    dimensions: ScorecardDimension[];
    disclaimer: string;
  };
  red_flags: { code: string; flags: RedFlag[]; clean: boolean; note: string };
}
export interface InvestorLensItem {
  key: string;
  name: string;
  persona: string;
  verdict: "supportive" | "mixed" | "caution" | "thin_data";
  score: number | null;
  summary: string;
  points: string[];
  checks?: {
    label: string;
    expected: string;
    actual: string;
    status: "pass" | "watch" | "fail" | "na";
  }[];
  watch_next: string[];
}
export interface InvestorLensResponse {
  code: string;
  as_of_date: string;
  headline: string;
  lenses: InvestorLensItem[];
  disclaimer: string;
}
export interface NoteBeat {
  handle: string;
  name: string;
  count: number;
}
export interface Desk {
  handle: string;
  name: string;
  bio: string;
  joined: string;
  posts: number;
  followers: number;
  following: boolean;
  verified: boolean;
  cadence: string;
  next_evaluation_at: string;
  methodology: string;
  post_rule: string;
  source_note: string;
  last_post_at: string | null;
}
export interface UserProfile {
  handle: string;
  name: string;
  joined: string;
  posts: number;
  portfolio_public: boolean;
}
export interface PublicHolding {
  code: string;
  name: string | null;
  quantity: number;
  avg_cost: number;
  ltp: number | null;
  value: number | null;
  day_change_pct: number | null;
  pnl: number | null;
  pnl_pct: number | null;
}
export interface PublicPortfolio {
  holdings: PublicHolding[];
  total_value: number | null;
  total_cost: number;
  day_pnl: number | null;
  day_pnl_pct: number | null;
  total_pnl: number | null;
  total_pnl_pct: number | null;
}
export type ReactionKind = "agree" | "disagree";
export interface Post {
  id: number;
  author: { handle: string; name: string };
  body: string;
  sentiment: "bull" | "bear" | null;
  cashtags: string[];
  cashtag_changes?: Record<string, number>;
  image_url: string | null;
  created_at: string;
  kind: "user" | "note";
  parent_id: number | null;
  reply_count: number;
  agree: number;
  disagree: number;
  my_reaction: ReactionKind | null;
  moderation_status?: string;
  moderation_reason?: string | null;
}
export interface User {
  id: number;
  handle: string;
  name: string;
  locale: string;
  role: string; // 'user' | 'admin'
  email: string | null;
  email_verified: boolean;
  phone: string | null;
  phone_verified: boolean;
  portfolio_public: boolean;
}

export interface InstitutionalLeadInput {
  organization: string;
  contact_name: string;
  work_email: string;
  role: string;
  use_case: string;
  source: string;
  consent: true;
  website: string;
}

export type BetaFeedbackKind = "useful" | "unclear" | "incorrect" | "missing" | "other";
export interface BetaFeedbackInput {
  kind: BetaFeedbackKind;
  message: string;
  path: string;
  symbol_code: string | null;
  contact_consent: boolean;
  website: string;
}

export const api = {
  productEvent: (
    name: string,
    properties: Record<string, string | number | boolean | null | undefined> = {},
  ) =>
    analyticsAllowed()
      ? request<{ status: string }>("/product-events", {
      method: "POST",
      body: JSON.stringify({
        name,
        analytics_consent: true,
        session_id: clientId(),
        path: typeof window === "undefined" ? null : window.location.pathname,
        properties,
      }),
        })
      : Promise.resolve({ status: "consent_required" }),
  institutionalLead: (body: InstitutionalLeadInput) =>
    request<{ status: string }>("/institutional-leads", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  betaFeedback: (body: BetaFeedbackInput) =>
    request<{ status: string }>("/beta-feedback", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  // auth
  register: (b: { name: string; contact: string; password: string }) =>
    request<{ access_token: string; refresh_token?: string }>("/auth/register", {
      method: "POST",
      body: JSON.stringify(b),
    }),
  login: (b: { identifier: string; password: string }) =>
    request<{ access_token: string; refresh_token?: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify(b),
    }),
  restoreSession: (refresh_token?: string | null) =>
    request<{ access_token: string; refresh_token?: string | null }>("/auth/refresh", {
      method: "POST",
      body: JSON.stringify(refresh_token ? { refresh_token } : {}),
    }),
  logout: (refresh_token?: string | null) =>
    request<{ status: string }>("/auth/logout", {
      method: "POST",
      body: JSON.stringify(refresh_token ? { refresh_token } : {}),
    }),
  forgotPassword: (email: string) =>
    request<{ status: string }>("/auth/forgot", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),
  resetPassword: (token: string, password: string) =>
    request<{ access_token: string; refresh_token?: string }>("/auth/reset", {
      method: "POST",
      body: JSON.stringify({ token, password }),
    }),
  verifyEmail: (token: string) =>
    request<{ status: string }>("/auth/verify", {
      method: "POST",
      body: JSON.stringify({ token }),
    }),
  me: () => request<User>("/auth/me"),
  updateContact: (b: { email?: string; phone?: string }) =>
    request<User>("/auth/me", { method: "PATCH", body: JSON.stringify(b) }),
  resendVerify: () =>
    request<{ status: string }>("/auth/resend-verify", { method: "POST" }),

  // market
  quotes: (codes?: string[]) =>
    request<Quote[]>(
      `/quotes${codes?.length ? `?codes=${codes.join(",")}` : ""}`,
    ),
  symbols: (limit = 500, q?: string) => {
    const params = new URLSearchParams({ limit: String(limit) });
    const query = q?.trim();
    if (query) params.set("q", query);
    return request<SymbolOut[]>(`/symbols?${params.toString()}`);
  },
  screens: (size?: string) =>
    request<ScreensResponse>(`/screens${size ? `?size=${encodeURIComponent(size)}` : ""}`),
  browseSize: (tier: string, limit = 50, offset = 0) =>
    request<BrowseSize>(`/browse/size/${tier}?limit=${limit}&offset=${offset}`),
  marketPulse: () => request<MarketPulse>("/market-pulse"),
  marketMood: () => request<MoodIndex>("/market-mood"),
  marketConfig: () => request<MarketConfig>("/market/config"),
  marketStatus: () => request<MarketStatus>("/market/status"),
  dailyShortlist: (size = 5, asOf?: string) => {
    const params = new URLSearchParams({ size: String(size) });
    if (asOf) params.set("as_of", asOf);
    return request<DailyShortlist>(`/shortlist/daily?${params.toString()}`);
  },
  dailyShortlistPerformance: () =>
    request<DailyShortlistPerformance>("/shortlist/daily/performance"),
  scannerRadar: (tab: string, watched: boolean, limit?: number, size?: string) => {
    const params = new URLSearchParams({ tab });
    if (watched) params.set("watched", "true");
    if (limit) params.set("limit", String(limit));
    if (size) params.set("size", size);
    return request<ScannerResponse>(`/scanner/radar?${params.toString()}`);
  },
  sectors: () => request<Sector[]>("/sectors"),
  screen: (
    key: string,
    limit = 50,
    period?: string,
    window?: string,
    direction?: string,
    size?: string,
  ) =>
    request<Screen>(
      `/screens/${key}?limit=${limit}${period ? `&period=${period}` : ""}${window ? `&window=${window}` : ""}${direction ? `&direction=${direction}` : ""}${size ? `&size=${size}` : ""}`,
    ),
  symbol: (code: string) => request<SymbolDetail>(`/symbols/${code}`),
  researchPreparation: (code: string) =>
    request<ResearchPreparation>(`/research-preparations/${encodeURIComponent(code)}`),
  prepareResearch: (code: string) =>
    request<ResearchPreparation>(`/research-preparations/${encodeURIComponent(code)}`, {
      method: "POST",
    }),

  bars: (code: string, limit = 180) =>
    request<Bar[]>(`/symbols/${code}/bars?limit=${limit}`),
  analytics: (code: string) => request<Analytics>(`/symbols/${code}/analytics`),
  levels: (code: string) =>
    request<{
      code: string;
      as_of: string;
      lines: string[];
      live_line: string | null;
    }>(`/symbols/${code}/levels`),
  explainer: (code: string) =>
    request<{
      code: string;
      as_of_date: string;
      headline: string;
      points: { tag: string; text: string }[];
    }>(`/symbols/${code}/explainer`),
  digest: (code: string) => request<Digest>(`/symbols/${code}/digest`),
  research: (code: string, q: string, lang: "en" | "bn" = "en") =>
    request<ResearchBrief>(
      `/symbols/${code}/research?q=${encodeURIComponent(q)}&lang=${encodeURIComponent(lang)}`,
    ),
  plainRead: (code: string) =>
    request<PlainRead>(`/symbols/${code}/plain-read`),
  scorecard: (code: string) =>
    request<ScorecardResponse>(`/symbols/${code}/scorecard`),
  investorLens: (code: string) =>
    request<InvestorLensResponse>(`/symbols/${code}/investor-lens`),
  buzz: (code: string) => request<Buzz>(`/symbols/${code}/buzz`),
  company: (code: string) => request<Company>(`/symbols/${code}/company`),
  institutionalHoldings: (code: string) =>
    request<InstitutionalActivity>(`/symbols/${code}/institutional-holdings`),
  shortVolume: (code: string) =>
    request<ShortVolumeActivity>(`/symbols/${code}/short-volume`),
  pulse: (code: string) => request<Pulse>(`/symbols/${code}/pulse`),
  news: (code: string) => request<NewsItem[]>(`/symbols/${code}/news`),
  recordView: (code: string) =>
    analyticsAllowed()
      ? request<void>(`/symbols/${code}/view`, {
          method: "POST",
          body: JSON.stringify({ analytics_consent: true, session_id: clientId() }),
        })
      : Promise.resolve(),
  trending: (days = 2, limit = 10) =>
    request<WatchItem[]>(`/trending?days=${days}&limit=${limit}`),
  trendingStocks: (limit = 15) =>
    request<TrendingStock[]>(`/trending-stocks?limit=${limit}`),
  todaysWatch: () => request<TodaysWatch>("/todays-watch"),
  earningsCalendar: (days = 7, back = 0, perDay = 4) =>
    request<EarningsEvent[]>(
      `/market/earnings-calendar?days=${days}&back=${back}&per_day=${perDay}`,
    ),

  // posts
  feed: (
    code?: string,
    kind?: "note" | "user",
    limit?: number,
    offset?: number,
    author?: string,
    watched?: boolean,
    portfolio?: boolean,
  ) => {
    const q = new URLSearchParams();
    if (code) q.set("code", code);
    if (kind) q.set("kind", kind);
    if (author) q.set("author", author);
    if (watched) q.set("watched", "true");
    if (portfolio) q.set("portfolio", "true");
    if (limit != null) q.set("limit", String(limit));
    if (offset != null) q.set("offset", String(offset));
    const s = q.toString();
    return request<Post[]>(`/posts${s ? `?${s}` : ""}`);
  },
  noteBeats: () => request<NoteBeat[]>("/posts/note-beats"),
  desk: (handle: string) => request<Desk>(`/desks/${handle}`),
  userProfile: (handle: string) => request<UserProfile>(`/users/${handle}`),
  userPortfolio: (handle: string) => request<PublicPortfolio>(`/users/${handle}/portfolio`),
  userPortfolioHistory: (handle: string, period: PortfolioHistoryPeriod) =>
    request<PortfolioHistoryPoint[]>(`/users/${handle}/portfolio/history?period=${period}`),
  portfolioSetVisibility: (isPublic: boolean) =>
    request<{ public: boolean }>("/portfolio/visibility", {
      method: "PATCH",
      body: JSON.stringify({ public: isPublic }),
    }),
  followDesk: (handle: string) =>
    request<{ status: string }>(`/desks/${handle}/follow`, { method: "POST" }),
  unfollowDesk: (handle: string) =>
    request<{ status: string }>(`/desks/${handle}/follow`, { method: "DELETE" }),
  createPost: (b: {
    body: string;
    sentiment: "bull" | "bear" | null;
    parent_id?: number;
    route_code?: string;
  }) => request<Post>("/posts", { method: "POST", body: JSON.stringify(b) }),
  topPost: (code: string) => request<Post | null>(`/posts/top?code=${code}`),
  deletePost: (id: number) => request<void>(`/posts/${id}`, { method: "DELETE" }),
  replies: (id: number) => request<Post[]>(`/posts/${id}/replies`),
  react: (id: number, kind: ReactionKind) =>
    request<{ status: string; kind: string }>(`/posts/${id}/react`, {
      method: "POST",
      body: JSON.stringify({ kind }),
    }),
  unreact: (id: number) =>
    request<void>(`/posts/${id}/react`, { method: "DELETE" }),

  // watchlist
  watchlist: () => request<SymbolDetail[]>("/watchlist"),
  watchAdd: (code: string) =>
    request<{ status: string }>("/watchlist", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),
  watchRemove: (code: string) =>
    request<void>(`/watchlist/${code}`, { method: "DELETE" }),

  // alerts
  alertsUnread: () => request<{ unread: number }>("/alerts/unread-count"),
  alerts: (limit = 30, offset = 0) =>
    request<AlertItem[]>(`/alerts?limit=${limit}&offset=${offset}`),
  alertsMarkRead: () =>
    request<{ status: string }>("/alerts/mark-read", { method: "POST" }),
  priceAlerts: (code: string) =>
    request<PriceAlert[]>(`/alerts/price?code=${code}`),
  priceAlertCreate: (b: { code: string; level: number; direction: "above" | "below" }) =>
    request<PriceAlert>("/alerts/price", { method: "POST", body: JSON.stringify(b) }),
  priceAlertDelete: (id: number) =>
    request<void>(`/alerts/price/${id}`, { method: "DELETE" }),

  // portfolio — manual entries only; we never touch a broker account
  portfolio: () => request<Portfolio>("/portfolio"),
  holdingUpsert: (b: { code: string; quantity: number; avg_cost: number }) =>
    request<{ status: "created" | "updated"; code: string }>("/portfolio/holdings", {
      method: "POST",
      body: JSON.stringify(b),
    }),
  holdingDelete: (code: string) =>
    request<void>(`/portfolio/holdings/${code}`, { method: "DELETE" }),
  portfolioHistory: (period: PortfolioHistoryPeriod) =>
    request<PortfolioHistoryPoint[]>(`/portfolio/history?period=${period}`),

  // daily quiz — gamified learning, never trading
  quizToday: () => request<QuizToday>("/quiz/today"),
  quizAnswer: (question_id: number, choice_idx: number) =>
    request<QuizToday>("/quiz/answer", {
      method: "POST",
      body: JSON.stringify({ question_id, choice_idx }),
    }),

  // admin cockpit — the agent model portfolios (X-Admin-Token gated, read-only)
  adminAgents: (adminToken: string) =>
    request<AgentSummary[]>("/admin/agents", {
      headers: { "X-Admin-Token": adminToken },
    }),
  adminAgentDetail: (adminToken: string, handle: string) =>
    request<AgentDetail>(`/admin/agents/${encodeURIComponent(handle)}`, {
      headers: { "X-Admin-Token": adminToken },
    }),
};

// ---- agent model portfolios (admin cockpit) ----
export interface AgentHolding {
  code: string;
  quantity: number;
  sellable_quantity: number; // matured shares — the rest is still inside T+2 settlement
  avg_cost: number;
  ltp: number | null;
  value: number | null;
  pnl_pct: number | null;
  as_of: string | null;
}
export interface AgentTrade {
  id: number;
  code: string;
  side: "buy" | "sell";
  quantity: number;
  price: number;
  fee: number;
  net_cash: number;
  trade_date: string;
  settles_on: string;
  settled: boolean;
  reason: string;
  quote_as_of: string;
}
export interface AgentSummary {
  handle: string;
  display_name: string;
  strategy: string;
  description: string;
  is_active: boolean;
  initial_capital: number;
  cash_settled: number;
  cash_pending: number;
  holdings_value: number | null;
  equity: number | null;
  pnl: number | null;
  pnl_pct: number | null;
  positions: number;
  trades_total: number;
  last_trade_at: string | null;
  quotes_as_of: string | null;
}
export interface AgentDetail extends AgentSummary {
  holdings: AgentHolding[];
  trades: AgentTrade[];
}

// ---- quiz ----
export type QuizToday = {
  question_id: number;
  topic: string;
  question: string;
  choices: string[];
  answered: boolean;
  your_choice: number | null;
  correct: boolean | null;
  answer_idx: number | null;
  explanation: string | null;
  streak: number;
  points: number;
};

// ---- alerts ----
export type AlertItem = {
  id: number;
  kind: string; // price_cross | signal | ownership | earnings
  code: string | null;
  title: string;
  body: string | null;
  created_at: string;
  read: boolean;
};
export type PriceAlert = {
  id: number;
  code: string;
  level: number;
  direction: "above" | "below";
  triggered_at: string | null;
};

// ---- portfolio ----
export type PortfolioHoldingOut = {
  code: string;
  name: string | null;
  quantity: number;
  avg_cost: number;
  ltp: number | null;
  as_of: string | null;
  value: number | null;
  day_change_pct: number | null;
  pnl: number | null;
  pnl_pct: number | null;
  latest_alert_title: string | null;
  latest_alert_at: string | null;
  has_price_alert: boolean;
};
export type Portfolio = {
  holdings: PortfolioHoldingOut[];
  total_value: number | null;
  total_cost: number;
  day_pnl: number | null;
  day_pnl_pct: number | null;
  total_pnl: number | null;
  total_pnl_pct: number | null;
};
export type PortfolioHistoryPeriod = "1w" | "1m" | "3m" | "6m" | "1y" | "all";
export type PortfolioHistoryPoint = {
  date: string;
  total_value: number | null;
  total_cost: number;
};
