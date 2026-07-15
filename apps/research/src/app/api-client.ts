import { researchDeployment, tenantRequestHeaders } from "./deployment";
import type { ResearchCompanyDossier } from "../features/company-dossier/model";
import type { ResearchQueueSnapshot } from "../features/research-queue/model";

export interface ResearchUser {
  id: number;
  name: string;
  handle: string;
}

export interface ResearchWorkspace {
  id: string;
  organizationId: string;
  organizationName: string;
  tenantId: string;
  market: "DSE" | "US";
  name: string;
  baseCurrency: "BDT" | "USD";
  organizationRole: string;
  workspaceRole: string | null;
}

interface Tokens {
  access_token: string;
  refresh_token?: string | null;
}

export class ResearchApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ResearchApiError";
  }
}

let accessToken: string | null = null;
const refreshKey = `bulls.atlas.${researchDeployment.tenant}.refresh`;

export const researchTokenStore = {
  set(tokens: Tokens) {
    accessToken = tokens.access_token;
    if (tokens.refresh_token) localStorage.setItem(refreshKey, tokens.refresh_token);
    else localStorage.removeItem(refreshKey);
  },
  clear() {
    accessToken = null;
    localStorage.removeItem(refreshKey);
  },
  refreshToken() {
    return localStorage.getItem(refreshKey);
  },
};

let refreshInFlight: Promise<boolean> | null = null;

async function parseError(response: Response): Promise<string> {
  const body = await response.json().catch(() => ({}));
  return typeof body?.detail === "string" ? body.detail : `Request failed (${response.status})`;
}

async function refreshSession(): Promise<boolean> {
  refreshInFlight ??= (async () => {
    const refreshToken = researchTokenStore.refreshToken();
    const response = await fetch(`${researchDeployment.apiUrl}/auth/refresh`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", ...tenantRequestHeaders() },
      body: JSON.stringify(refreshToken ? { refresh_token: refreshToken } : {}),
    });
    if (!response.ok) {
      researchTokenStore.clear();
      return false;
    }
    researchTokenStore.set((await response.json()) as Tokens);
    return true;
  })().finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

async function request<T>(path: string, init: RequestInit = {}, retried = false): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...tenantRequestHeaders(),
    ...(init.headers as Record<string, string> | undefined),
  };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  const response = await fetch(`${researchDeployment.apiUrl}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
  if (response.status === 401 && !retried && !path.startsWith("/auth/")) {
    if (await refreshSession()) return request<T>(path, init, true);
  }
  if (!response.ok) throw new ResearchApiError(response.status, await parseError(response));
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function assertWorkspaceBoundary(workspace: ResearchWorkspace): ResearchWorkspace {
  if (
    workspace.tenantId !== researchDeployment.tenant ||
    workspace.market !== researchDeployment.market
  ) {
    throw new ResearchApiError(502, "The API returned a workspace outside this research tenant");
  }
  return workspace;
}

function assertQueueBoundary(
  snapshot: ResearchQueueSnapshot,
  workspaceId: string,
): ResearchQueueSnapshot {
  const crossedBoundary =
    snapshot.tenantId !== researchDeployment.tenant ||
    snapshot.market !== researchDeployment.market ||
    snapshot.workspaceId !== workspaceId ||
    snapshot.candidates.some((candidate) => candidate.market !== researchDeployment.market);
  if (crossedBoundary) {
    throw new ResearchApiError(502, "The API returned research data outside this tenant boundary");
  }
  return snapshot;
}

function assertDossierBoundary(
  dossier: ResearchCompanyDossier,
  workspaceId: string,
  ticker: string,
): ResearchCompanyDossier {
  const crossedBoundary =
    dossier.tenantId !== researchDeployment.tenant ||
    dossier.market !== researchDeployment.market ||
    dossier.workspaceId !== workspaceId ||
    dossier.candidate.market !== researchDeployment.market ||
    dossier.candidate.ticker !== ticker.toUpperCase();
  if (crossedBoundary) {
    throw new ResearchApiError(502, "The API returned a dossier outside this tenant boundary");
  }
  return dossier;
}

export const researchApi = {
  async restore(): Promise<ResearchUser | null> {
    if (!(await refreshSession())) return null;
    return request<ResearchUser>("/auth/me");
  },
  async login(identifier: string, password: string): Promise<ResearchUser> {
    const tokens = await request<Tokens>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ identifier, password }),
    });
    researchTokenStore.set(tokens);
    return request<ResearchUser>("/auth/me");
  },
  async logout(): Promise<void> {
    const refreshToken = researchTokenStore.refreshToken();
    try {
      await request("/auth/logout", {
        method: "POST",
        body: JSON.stringify(refreshToken ? { refresh_token: refreshToken } : {}),
      });
    } finally {
      researchTokenStore.clear();
    }
  },
  async workspaces(): Promise<ResearchWorkspace[]> {
    const workspaces = await request<ResearchWorkspace[]>("/institutional-research/workspaces");
    return workspaces.map(assertWorkspaceBoundary);
  },
  async bootstrapWorkspace(): Promise<ResearchWorkspace> {
    return assertWorkspaceBoundary(
      await request<ResearchWorkspace>("/institutional-research/workspaces/bootstrap", {
        method: "POST",
      }),
    );
  },
  async queue(
    workspaceId: string,
    filters: { capTier?: string; query?: string } = {},
    signal?: AbortSignal,
  ): Promise<ResearchQueueSnapshot> {
    const parameters = new URLSearchParams();
    if (filters.capTier && filters.capTier !== "all") {
      parameters.set("cap_tier", filters.capTier);
    }
    if (filters.query?.trim()) parameters.set("query", filters.query.trim());
    const queryString = parameters.size ? `?${parameters.toString()}` : "";
    const snapshot = await request<ResearchQueueSnapshot>(
      `/institutional-research/workspaces/${encodeURIComponent(workspaceId)}/queue${queryString}`,
      { signal },
    );
    return assertQueueBoundary(snapshot, workspaceId);
  },
  async dossier(
    workspaceId: string,
    ticker: string,
    signal?: AbortSignal,
  ): Promise<ResearchCompanyDossier> {
    const normalizedTicker = ticker.trim().toUpperCase();
    const dossier = await request<ResearchCompanyDossier>(
      `/institutional-research/workspaces/${encodeURIComponent(workspaceId)}/companies/${encodeURIComponent(normalizedTicker)}`,
      { signal },
    );
    return assertDossierBoundary(dossier, workspaceId, normalizedTicker);
  },
};
