// Minimal typed API client. Token is injected from localStorage.
// Use 127.0.0.1 (not "localhost") so the browser doesn't try IPv6 ::1 first,
// which the API doesn't bind. Override with VITE_API_BASE if needed.
const BASE = (import.meta.env.VITE_API_BASE as string) || "http://127.0.0.1:8090";
const TOKEN_KEY = "bulls.token";

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

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
export interface Post {
  id: number;
  author: { handle: string; name: string };
  body: string;
  sentiment: "bull" | "bear" | null;
  cashtags: string[];
  created_at: string;
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
    request<Quote[]>(`/quotes${codes?.length ? `?codes=${codes.join(",")}` : ""}`),
  symbol: (code: string) => request<SymbolDetail>(`/symbols/${code}`),

  // posts
  feed: (code?: string) => request<Post[]>(`/posts${code ? `?code=${code}` : ""}`),
  createPost: (b: { body: string; sentiment: "bull" | "bear" | null }) =>
    request<Post>("/posts", { method: "POST", body: JSON.stringify(b) }),

  // watchlist
  watchlist: () => request<SymbolDetail[]>("/watchlist"),
  watchAdd: (code: string) =>
    request<{ status: string }>("/watchlist", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),
  watchRemove: (code: string) => request<void>(`/watchlist/${code}`, { method: "DELETE" }),
};
