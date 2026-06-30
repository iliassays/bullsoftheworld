import { currentLang } from "./i18n";

// Minimal typed API client. Token is injected from localStorage.
// Use 127.0.0.1 (not "localhost") so the browser doesn't try IPv6 ::1 first,
// which the API doesn't bind. Override with VITE_API_BASE if needed.
const BASE =
  (import.meta.env.VITE_API_BASE as string) || "http://127.0.0.1:8090";
const TOKEN_KEY = "bulls.token";

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

// Stable anonymous client id so page views can be de-duped without a login.
const CID_KEY = "bulls.cid";
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

async function request<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-Locale": currentLang(),
    ...(opts.headers as Record<string, string>),
  };
  const token = tokenStore.get();
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, { ...opts, headers });
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
}
export interface SymbolDetail {
  symbol: SymbolOut;
  quote: Quote | null;
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
export interface Level {
  value: number;
  date: string;
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
  period_spark?: number[]; // ownership: price over the disclosure window (oldest→newest)
  category?: string | null;
  adtv_mn?: number | null;
  turnover_mn?: number | null;
  safe_order_mn?: number | null;
  market_cap_mn?: number | null;
  free_float_cap_mn?: number | null;
  liquidity?: string | null;
  setup_quality?: string | null;
  why?: string | null;
  catalyst?: string | null;
  catalyst_date?: string | null;
  catalyst_category?: string | null;
}
export interface Screen {
  key: string;
  title: string;
  description: string;
  value_label: string;
  group: string;
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
export interface ScreensResponse {
  as_of: string | null; // EOD analytics date — screen rankings are as-of this close
  quote_as_of?: string | null; // latest 15-min quote snapshot — price/"today's move" freshness
  methodology?: MarketMethodology;
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
  dsex: number | null;
  dsex_change_pct: number | null;
  turnover_cr: number | null;
  turnover_vs_20d: number | null;
  advancers: number;
  decliners: number;
  unchanged: number;
  total: number;
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
export interface Company {
  code: string;
  fundamentals: {
    market_cap_mn: number | null;
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
    institute_pct: number | null;
    foreign_pct: number | null;
    public_pct: number | null;
    institute_delta: number | null;
    foreign_delta: number | null;
    as_of: string | null;
    history: {
      as_of: string;
      sponsor: number | null;
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
    bonus_pct: number | null;
  }[];
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
}
export interface NewsItem {
  published_at: string;
  category: string;
  strength: number;
  headline: string;
  details?: NewsDetails | null;
}
export interface TrendingReason {
  kind: "volume" | "turnover" | "near_high" | "near_low" | "move" | "limit_up" | "limit_down";
  mult?: number;
  cr?: number;
  pct?: number;
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
export interface MoodComponent {
  key: string;
  label: string;
  score: number;
  detail: string;
}
export interface MoodIndex {
  as_of_date: string;
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
export type ReactionKind = "agree" | "disagree";
export interface Post {
  id: number;
  author: { handle: string; name: string };
  body: string;
  sentiment: "bull" | "bear" | null;
  cashtags: string[];
  image_url: string | null;
  created_at: string;
  kind: "user" | "note";
  parent_id: number | null;
  reply_count: number;
  agree: number;
  disagree: number;
  my_reaction: ReactionKind | null;
}
export interface User {
  id: number;
  handle: string;
  name: string;
  locale: string;
  email: string | null;
  email_verified: boolean;
  phone: string | null;
  phone_verified: boolean;
}

export const api = {
  // auth
  register: (b: { name: string; contact: string; password: string }) =>
    request<{ access_token: string }>("/auth/register", {
      method: "POST",
      body: JSON.stringify(b),
    }),
  login: (b: { identifier: string; password: string }) =>
    request<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify(b),
    }),
  forgotPassword: (email: string) =>
    request<{ status: string }>("/auth/forgot", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),
  resetPassword: (token: string, password: string) =>
    request<{ access_token: string }>("/auth/reset", {
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
  symbols: (limit = 500) => request<SymbolOut[]>(`/symbols?limit=${limit}`),
  screens: () => request<ScreensResponse>("/screens"),
  marketPulse: () => request<MarketPulse>("/market-pulse"),
  marketMood: () => request<MoodIndex>("/market-mood"),
  sectors: () => request<Sector[]>("/sectors"),
  screen: (
    key: string,
    limit = 50,
    period?: string,
    window?: string,
    direction?: string,
  ) =>
    request<Screen>(
      `/screens/${key}?limit=${limit}${period ? `&period=${period}` : ""}${window ? `&window=${window}` : ""}${direction ? `&direction=${direction}` : ""}`,
    ),
  symbol: (code: string) => request<SymbolDetail>(`/symbols/${code}`),

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
  plainRead: (code: string) =>
    request<PlainRead>(`/symbols/${code}/plain-read`),
  buzz: (code: string) => request<Buzz>(`/symbols/${code}/buzz`),
  company: (code: string) => request<Company>(`/symbols/${code}/company`),
  pulse: (code: string) => request<Pulse>(`/symbols/${code}/pulse`),
  news: (code: string) => request<NewsItem[]>(`/symbols/${code}/news`),
  recordView: (code: string) =>
    request<void>(`/symbols/${code}/view`, {
      method: "POST",
      body: JSON.stringify({ session_id: clientId() }),
    }),
  trending: (days = 2, limit = 10) =>
    request<WatchItem[]>(`/trending?days=${days}&limit=${limit}`),
  trendingStocks: (limit = 15) =>
    request<TrendingStock[]>(`/trending-stocks?limit=${limit}`),
  todaysWatch: () => request<TodaysWatch>("/todays-watch"),

  // posts
  feed: (code?: string, kind?: "note", limit?: number, offset?: number) => {
    const q = new URLSearchParams();
    if (code) q.set("code", code);
    if (kind) q.set("kind", kind);
    if (limit != null) q.set("limit", String(limit));
    if (offset != null) q.set("offset", String(offset));
    const s = q.toString();
    return request<Post[]>(`/posts${s ? `?${s}` : ""}`);
  },
  createPost: (b: {
    body: string;
    sentiment: "bull" | "bear" | null;
    parent_id?: number;
  }) => request<Post>("/posts", { method: "POST", body: JSON.stringify(b) }),
  topPost: (code: string) => request<Post | null>(`/posts/top?code=${code}`),
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
};
