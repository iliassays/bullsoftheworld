// Cockpit API client — admin-only endpoints, authenticated with X-Admin-Token.
// No consumer login here; the token is the single ops credential, kept only for this tab session.

const BASE = (import.meta.env.VITE_API_BASE as string) || "http://127.0.0.1:8090";
const ADMIN_TOKEN_KEY = "bulls.admintoken";
const TENANT_HOST = (import.meta.env.VITE_TENANT_HOST as string) || "bullsofdhaka.com";

export const adminTokenStore = {
  get: () => sessionStorage.getItem(ADMIN_TOKEN_KEY),
  set: (token: string) => {
    sessionStorage.setItem(ADMIN_TOKEN_KEY, token);
    localStorage.removeItem(ADMIN_TOKEN_KEY);
  },
  clear: () => {
    sessionStorage.removeItem(ADMIN_TOKEN_KEY);
    localStorage.removeItem(ADMIN_TOKEN_KEY);
  },
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
  const token = adminTokenStore.get();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-Tenant-Host": TENANT_HOST,
    ...(token ? { "X-Admin-Token": token } : {}),
    ...(opts.headers as Record<string, string>),
  };
  const res = await fetch(`${BASE}${path}`, { ...opts, headers });
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = body?.detail;
    const msg = typeof d === "string" ? d : d?.reason || d?.error || res.statusText;
    throw new ApiError(res.status, msg);
  }
  return body as T;
}

export interface AdminTenant {
  name: string;
  display_name: string;
  market: string;
}
export interface AdminRecentEvent {
  post_id: number;
  decision: string;
  categories: string[];
  reason_code: string | null;
  layer: number;
  created_at: string;
}
export interface AdminOverview {
  tenant: string;
  market: string;
  generated_at: string;
  users_people: number;
  users_desks: number;
  posts_total: number;
  user_posts: number;
  agent_notes: number;
  people_posts_today: number;
  agent_notes_today: number;
  reactions_7d: number;
  moderation: Record<string, number>;
  review_pending: number;
  flagged_24h: number;
  recent_events: AdminRecentEvent[];
  top_cashtags: { code: string; posts: number }[];
  last_eod_date: string | null;
  latest_quote_as_of: string | null;
  symbols_active: number;
  symbols_hidden: number;
}
export interface ModQueueItem {
  post_id: number;
  author_handle: string;
  author_name: string;
  account_age_days: number | null;
  body: string;
  cashtags: string[];
  status: string;
  reason: string | null;
  categories: string[];
  risk_score: number | null;
  rule_ids: string[];
  created_at: string;
}

export interface DailyPoint {
  date: string;
  signups: number;
  public_posts: number;
  agent_notes: number;
  reactions: number;
}
export interface Analytics {
  tenant: string;
  market: string;
  tz: string;
  days: number;
  generated_at: string;
  kpis: {
    people_total: number;
    desks_total: number;
    new_people_7d: number;
    new_people_30d: number;
    active_people_7d: number;
    public_posts_total: number;
    agent_notes_total: number;
    human_share_pct: number;
    reactions_7d: number;
  };
  series: DailyPoint[];
}

export const api = {
  tenants: () => request<AdminTenant[]>("/admin/tenants"),
  overview: (tenant: string) =>
    request<AdminOverview>(`/admin/overview?tenant=${encodeURIComponent(tenant)}`),
  analytics: (tenant: string, days: number) =>
    request<Analytics>(`/admin/analytics?tenant=${encodeURIComponent(tenant)}&days=${days}`),
  modQueue: (tenant: string, status: "pending" | "held") =>
    request<{ count: number; items: ModQueueItem[] }>(
      `/moderation/queue?tenant=${encodeURIComponent(tenant)}&status=${status}`,
    ),
  modApprove: (tenant: string, postId: number) =>
    request<{ status: string }>(
      `/moderation/${postId}/approve?tenant=${encodeURIComponent(tenant)}`,
      { method: "POST", body: "{}" },
    ),
  modBlock: (tenant: string, postId: number) =>
    request<{ status: string }>(
      `/moderation/${postId}/block?tenant=${encodeURIComponent(tenant)}`,
      { method: "POST", body: "{}" },
    ),
};
