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
    ...(opts.headers as Record<string, string>),
  };
  const token = tokenStore.get();
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, { ...opts, headers });
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, body?.detail ?? res.statusText);
  return body as T;
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
export interface ScreenItem {
  code: string;
  last_close: number;
  value: number;
}
export interface Screen {
  key: string;
  title: string;
  description: string;
  value_label: string;
  items: ScreenItem[];
}
export interface ScreensResponse {
  as_of: string | null;
  screens: Screen[];
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
export type ReactionKind = "agree" | "disagree";
export interface Post {
  id: number;
  author: { handle: string; name: string };
  body: string;
  sentiment: "bull" | "bear" | null;
  cashtags: string[];
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
}

export const api = {
  // auth
  register: (b: { handle: string; name: string; password: string }) =>
    request<{ access_token: string }>("/auth/register", {
      method: "POST",
      body: JSON.stringify(b),
    }),
  login: (b: { handle: string; password: string }) =>
    request<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify(b),
    }),
  me: () => request<User>("/auth/me"),

  // market
  quotes: (codes?: string[]) =>
    request<Quote[]>(
      `/quotes${codes?.length ? `?codes=${codes.join(",")}` : ""}`,
    ),
  symbols: (limit = 500) => request<SymbolOut[]>(`/symbols?limit=${limit}`),
  screens: () => request<ScreensResponse>("/screens"),
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
    request<{ code: string; explanation: string; as_of_date: string }>(
      `/symbols/${code}/explainer`,
    ),
  digest: (code: string) => request<Digest>(`/symbols/${code}/digest`),
  buzz: (code: string) => request<Buzz>(`/symbols/${code}/buzz`),
  recordView: (code: string) =>
    request<void>(`/symbols/${code}/view`, {
      method: "POST",
      body: JSON.stringify({ session_id: clientId() }),
    }),
  trending: (days = 2, limit = 10) =>
    request<WatchItem[]>(`/trending?days=${days}&limit=${limit}`),
  todaysWatch: () => request<TodaysWatch>("/todays-watch"),
  translatePost: (text: string) =>
    request<{ text: string; language: string }>("/translate", {
      method: "POST",
      body: JSON.stringify({ text }),
    }),

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
