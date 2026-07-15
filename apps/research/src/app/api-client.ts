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

export interface ResearchRunStep {
  ordinal: number;
  kind: string;
  status: string;
  output: Record<string, unknown>;
  metrics: Record<string, unknown>;
}

export interface ResearchClaim {
  ordinal: number;
  claimType: string;
  statement: string;
  verdict: string;
  confidence: number;
  values: Record<string, unknown>;
  verification: Record<string, unknown>;
}

export interface ResearchRun {
  id: string;
  workspaceId: string;
  tenantId: string;
  market: "DSE" | "US";
  runKind: "deep_research" | "hypothesis" | string;
  status: string;
  question: string;
  code: string | null;
  parameters: Record<string, unknown>;
  knowledgeCutoffAt: string;
  provider: string | null;
  model: string | null;
  codeVersion: string;
  evidenceSnapshotHash: string | null;
  requestedAt: string;
  completedAt: string | null;
  steps: ResearchRunStep[];
  claims: ResearchClaim[];
}

export interface ShadowSnapshot {
  id: string;
  asOfDate: string;
  sessionNumber: number;
  nav: number;
  cash: number;
  benchmarkNav: number;
  peakNav: number;
  grossExposurePct: number;
  drawdownPct: number;
  cumulativeFees: number;
  cumulativeTurnover: number;
  positions: Record<string, { shares: number; average_cost: number }>;
  targetWeights: Record<string, number>;
  trades: Array<Record<string, unknown>>;
  riskInterventions: Array<Record<string, unknown>>;
}

export interface ShadowPortfolio {
  id: string;
  workspaceId: string;
  tenantId: string;
  market: "DSE" | "US";
  sourceRunId: string;
  name: string;
  strategyKey: string;
  status: "active" | "paused" | "archived";
  initialCapital: number;
  inceptionDate: string;
  lastEvaluatedOn: string | null;
  configuration: Record<string, unknown>;
  snapshots: ShadowSnapshot[];
}

export interface CalibrationObservation {
  id: string;
  runId: string;
  code: string;
  signalStatus: string;
  confidence: number;
  referenceDate: string;
  referencePrice: number;
  horizonSessions: number;
  status: string;
  outcomeDate: string | null;
  outcomePrice: number | null;
  returnPct: number | null;
  maxAdversePct: number | null;
  maxFavorablePct: number | null;
}

export interface CalibrationSnapshot {
  workspaceId: string;
  tenantId: string;
  market: "DSE" | "US";
  pending: number;
  matured: number;
  buckets: Array<{
    signalStatus: string;
    horizonSessions: number;
    observations: number;
    averageReturnPct: number;
    positiveRatePct: number;
  }>;
  observations: CalibrationObservation[];
}

export interface AutomationPolicy {
  id: string;
  workspaceId: string;
  tenantId: string;
  market: "DSE" | "US";
  enabled: boolean;
  queueLimit: number;
  researchLimit: number;
  capTier: string | null;
  strategyKey: "dse_reversal_v1" | "us_breakout_v1";
  universeLimit: number;
  initialCapital: number;
  nextRunAt: string | null;
  lastStartedAt: string | null;
  lastCompletedAt: string | null;
  lastRunStatus: "queued" | "running" | "succeeded" | "failed" | null;
  lastError: string | null;
}

export interface AutomationPolicyInput {
  enabled: boolean;
  queue_limit: number;
  research_limit: number;
  cap_tier: string | null;
  strategy_key: "dse_reversal_v1" | "us_breakout_v1";
  universe_limit: number;
  initial_capital: number;
}

export interface LifecycleDispatch {
  accepted: boolean;
  jobId: string;
  scheduledFor: string;
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

function assertRunBoundary(run: ResearchRun, workspaceId: string): ResearchRun {
  if (
    run.tenantId !== researchDeployment.tenant ||
    run.market !== researchDeployment.market ||
    run.workspaceId !== workspaceId
  ) {
    throw new ResearchApiError(502, "The API returned a research run outside this tenant boundary");
  }
  return run;
}

function assertPortfolioBoundary(
  portfolio: ShadowPortfolio,
  workspaceId: string,
): ShadowPortfolio {
  if (
    portfolio.tenantId !== researchDeployment.tenant ||
    portfolio.market !== researchDeployment.market ||
    portfolio.workspaceId !== workspaceId
  ) {
    throw new ResearchApiError(502, "The API returned a shadow book outside this tenant boundary");
  }
  return portfolio;
}

function assertAutomationBoundary(
  policy: AutomationPolicy,
  workspaceId: string,
): AutomationPolicy {
  if (
    policy.tenantId !== researchDeployment.tenant ||
    policy.market !== researchDeployment.market ||
    policy.workspaceId !== workspaceId
  ) {
    throw new ResearchApiError(502, "The API returned automation data outside this tenant boundary");
  }
  return policy;
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
  async startCompanyResearch(workspaceId: string, ticker: string): Promise<ResearchRun> {
    const normalizedTicker = ticker.trim().toUpperCase();
    const run = await request<ResearchRun>(
      `/institutional-research/workspaces/${encodeURIComponent(workspaceId)}/companies/${encodeURIComponent(normalizedTicker)}/research-runs`,
      {
        method: "POST",
        body: JSON.stringify({ idempotency_key: crypto.randomUUID() }),
      },
    );
    return assertRunBoundary(run, workspaceId);
  },
  async backtest(
    workspaceId: string,
    payload: {
      strategy_key: "dse_reversal_v1" | "us_breakout_v1";
      start_date?: string;
      end_date?: string;
      cap_tier?: string;
      universe_limit: number;
      initial_capital: number;
    },
  ): Promise<ResearchRun> {
    const run = await request<ResearchRun>(
      `/institutional-research/workspaces/${encodeURIComponent(workspaceId)}/backtests`,
      {
        method: "POST",
        body: JSON.stringify({ ...payload, idempotency_key: crypto.randomUUID() }),
      },
    );
    return assertRunBoundary(run, workspaceId);
  },
  async runs(workspaceId: string): Promise<ResearchRun[]> {
    const runs = await request<ResearchRun[]>(
      `/institutional-research/workspaces/${encodeURIComponent(workspaceId)}/runs`,
    );
    return runs.map((run) => assertRunBoundary(run, workspaceId));
  },
  async run(workspaceId: string, runId: string): Promise<ResearchRun> {
    return assertRunBoundary(
      await request<ResearchRun>(
        `/institutional-research/workspaces/${encodeURIComponent(workspaceId)}/runs/${encodeURIComponent(runId)}`,
      ),
      workspaceId,
    );
  },
  async createShadowPortfolio(
    workspaceId: string,
    sourceRunId: string,
    name: string,
  ): Promise<ShadowPortfolio> {
    const portfolio = await request<ShadowPortfolio>(
      `/institutional-research/workspaces/${encodeURIComponent(workspaceId)}/shadow-portfolios`,
      {
        method: "POST",
        body: JSON.stringify({ source_run_id: sourceRunId, name }),
      },
    );
    return assertPortfolioBoundary(portfolio, workspaceId);
  },
  async shadowPortfolios(workspaceId: string): Promise<ShadowPortfolio[]> {
    const portfolios = await request<ShadowPortfolio[]>(
      `/institutional-research/workspaces/${encodeURIComponent(workspaceId)}/shadow-portfolios`,
    );
    return portfolios.map((portfolio) => assertPortfolioBoundary(portfolio, workspaceId));
  },
  async reconcileShadowPortfolios(workspaceId: string): Promise<ShadowPortfolio[]> {
    const portfolios = await request<ShadowPortfolio[]>(
      `/institutional-research/workspaces/${encodeURIComponent(workspaceId)}/shadow-portfolios/reconcile`,
      { method: "POST" },
    );
    return portfolios.map((portfolio) => assertPortfolioBoundary(portfolio, workspaceId));
  },
  async calibration(workspaceId: string): Promise<CalibrationSnapshot> {
    const snapshot = await request<CalibrationSnapshot>(
      `/institutional-research/workspaces/${encodeURIComponent(workspaceId)}/calibration`,
    );
    if (
      snapshot.workspaceId !== workspaceId ||
      snapshot.tenantId !== researchDeployment.tenant ||
      snapshot.market !== researchDeployment.market
    ) {
      throw new ResearchApiError(502, "The API returned calibration data outside this tenant boundary");
    }
    return snapshot;
  },
  async automationPolicy(workspaceId: string): Promise<AutomationPolicy | null> {
    const policy = await request<AutomationPolicy | null>(
      `/institutional-research/workspaces/${encodeURIComponent(workspaceId)}/automation`,
    );
    return policy ? assertAutomationBoundary(policy, workspaceId) : null;
  },
  async configureAutomation(
    workspaceId: string,
    payload: AutomationPolicyInput,
  ): Promise<AutomationPolicy> {
    return assertAutomationBoundary(
      await request<AutomationPolicy>(
        `/institutional-research/workspaces/${encodeURIComponent(workspaceId)}/automation`,
        { method: "PUT", body: JSON.stringify(payload) },
      ),
      workspaceId,
    );
  },
  async runLifecycle(workspaceId: string): Promise<LifecycleDispatch> {
    return request<LifecycleDispatch>(
      `/institutional-research/workspaces/${encodeURIComponent(workspaceId)}/automation/run`,
      { method: "POST" },
    );
  },
};
