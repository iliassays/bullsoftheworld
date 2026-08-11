import { researchDeployment, tenantRequestHeaders } from "./deployment";
import type { ResearchCompanyDossier } from "../features/company-dossier/model";
import type { CatalystCalendar } from "../features/catalyst-calendar/model";
import type {
  ConditionKey,
  ConditionScan,
  ConditionSubscription,
} from "../features/condition-scanner/model";
import type { OptionChainPreview } from "../features/options-lens/model";
import type { ResearchQueueSnapshot } from "../features/research-queue/model";

export interface ResearchUser {
  id: number;
  name: string;
  handle: string;
  role: "user" | "admin";
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
  citations: Array<{
    evidenceDocumentId: string;
    evidenceSpanId: string;
    sourceType: string;
    sourceRecordId: string;
    title: string;
    sourceUrl: string | null;
    publishedAt: string | null;
    knownAt: string;
    factKey: string | null;
    text: string;
    relation: string;
    relevance: number;
  }>;
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

export type BacktestStrategyKey =
  | "dse_reversal_v1"
  | "dse_compression_breakout_20d_v1"
  | "dse_selective_compression_v1"
  | "us_breakout_v1"
  | "us_activist_13d_v1"
  | "us_insider_cluster_v1"
  | "us_forced_seller_v1"
  | "us_factor_sleeve_v1";

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

export interface InvestmentMandate {
  id: string;
  workspaceId: string;
  tenantId: string;
  market: "DSE" | "US";
  version: number;
  status: "active" | "superseded";
  objective: string;
  benchmarkKey: string;
  maxGrossExposurePct: number;
  minCashReservePct: number;
  maxPositionWeightPct: number;
  maxSectorWeightPct: number;
  maxAdvParticipationPct: number;
  portfolioDrawdownBrakePct: number;
  stressLossLimitPct: number;
  specificationHash: string;
  effectiveAt: string;
  supersededAt: string | null;
}

export interface InvestmentMandateInput {
  objective: string;
  benchmark_key: string;
  max_gross_exposure_pct: number;
  min_cash_reserve_pct: number;
  max_position_weight_pct: number;
  max_sector_weight_pct: number;
  max_adv_participation_pct: number;
  portfolio_drawdown_brake_pct: number;
  stress_loss_limit_pct: number;
}

export interface StrategyTrial {
  id: string;
  sourceRunId: string;
  workspaceId: string;
  tenantId: string;
  market: "DSE" | "US";
  strategyKey: string;
  strategyVersion: string;
  status: string;
  registrationState: "preregistered" | "legacy_reconstructed";
  trialSequence: number;
  multipleTestingPolicy: string;
  economicHypothesis: string;
  specification: Record<string, unknown>;
  specificationHash: string;
  outcome: Record<string, unknown>;
  registeredAt: string;
  completedAt: string | null;
}

export interface DecisionEvent {
  id: string;
  portfolioId: string;
  snapshotId: string;
  correlationId: string;
  sequence: number;
  eventKey: string;
  causedByEventKey: string | null;
  eventType: "signal" | "target" | "order" | "rejection" | "fill" | "position" | "risk" | "outcome";
  eventState: string;
  code: string | null;
  effectiveDate: string;
  payload: Record<string, unknown>;
  payloadHash: string;
  recordedAt: string;
}

export interface PortfolioOperatingAnalytics {
  portfolioId: string;
  asOfDate: string | null;
  mandate: InvestmentMandate;
  mandateVersion: number;
  mandateBinding: "pinned" | "legacy_active_fallback";
  risk: {
    grossExposurePct: number;
    cashReservePct: number;
    largestPositionPct: number;
    largestSectorPct: number;
    concentrationHhi: number;
    effectivePositions: number;
    weightedAverageCorrelation: number | null;
    maximumPairCorrelation: number | null;
    maximumExitDays: number | null;
    limitChecks: Array<{
      key: string;
      status: "within_limit" | "breached" | "unavailable";
      actual: number | null;
      limit: number;
      unit: "pct" | "days";
      detail: string;
    }>;
    stressScenarios: Array<{
      key: string;
      label: string;
      shockPct: number;
      estimatedLossPct: number;
      status: "within_limit" | "breached";
      methodology: string;
    }>;
    breachedLimits: string[];
    dataQualityNotes: string[];
  };
  attribution: {
    portfolioReturnPct: number;
    benchmarkReturnPct: number;
    excessReturnPct: number;
    components: Array<{
      key: string;
      label: string;
      contributionPct: number | null;
      quality: "exact" | "proxy" | "unavailable";
      explanation: string;
    }>;
    rejectedActions: number;
    methodologyVersion: string;
  };
  recentEvents: DecisionEvent[];
}

export interface InvestmentOperatingView {
  workspaceId: string;
  tenantId: string;
  market: "DSE" | "US";
  generatedAt: string;
  mandate: InvestmentMandate;
  trials: StrategyTrial[];
  portfolios: PortfolioOperatingAnalytics[];
}

export type SqueezeState =
  | "watch"
  | "forming"
  | "trigger_ready"
  | "confirmed"
  | "exhausted"
  | "failed";

export interface SqueezeEntry {
  evidenceMode: "forward" | "reconstructed";
  market: "DSE" | "US";
  code: string;
  company: string;
  capTier: string;
  family: string;
  familyLabel: string;
  state: SqueezeState;
  previousState: string | null;
  stateReason: string;
  isNew: boolean;
  isNewConfirmation: boolean;
  firstDiscoveredOn: string;
  asOfDate: string;
  sessionsSinceDiscovery: number;
  discoveryPrice: number | null;
  asOfPrice: number | null;
  returnSinceDiscoveryPct: number | null;
  firstConfirmedOn: string | null;
  confirmationPrice: number | null;
  moveToConfirmationPct: number | null;
  nextObservableOn: string | null;
  nextObservablePrice: number | null;
  returnSinceNextObservablePct: number | null;
  // Close-to-close. maxAdversePct can read 0.00% for a setup that traded well against you.
  maxFavorablePct: number | null;
  maxAdversePct: number | null;
  // Highest high / lowest low traded after the discovery close — excursions, not returns.
  peakTradedPct: number | null;
  troughTradedPct: number | null;
  setupPrice: number | null;
  triggerPrice: number | null;
  invalidationPrice: number | null;
  riskPerShare: number | null;
  planningObjectivePrice: number | null;
  planningRewardRisk: number | null;
  expectedHolding: string;
  liquidityCapacityNote: string;
  supportingEvidence: string[];
  counterEvidence: string[];
  dataQuality: string[];
  missingEvidence: string[];
  paperBookStatus: string;
  methodologyVersion: string;
}

export interface SqueezeFamily {
  family: string;
  label: string;
  status: "available" | "data_blocked" | "not_implemented";
  blockedReason: string | null;
  missingDatasets: string[];
  entries: SqueezeEntry[];
}

export interface SqueezeMonitor {
  market: "DSE" | "US";
  tenantId: string;
  generatedAt: string;
  selectedDate: string | null;
  latestDate: string | null;
  availableDates: string[];
  methodologyVersion: string;
  families: SqueezeFamily[];
  methodology: string;
  limitations: string[];
}

export interface SqueezeChartPoint {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  ema20: number | null;
  ema50: number | null;
  anchoredVwap: number | null;
}

export interface SqueezeStateMarker {
  date: string;
  state: string;
  previousState: string | null;
  reason: string;
  evidenceMode: "forward" | "reconstructed";
  methodologyVersion: string;
  episodeNumber: number;
  isCurrentEpisode: boolean;
}

export interface SqueezePath {
  market: "DSE" | "US";
  tenantId: string;
  family: string;
  familyLabel: string;
  entry: SqueezeEntry;
  points: SqueezeChartPoint[];
  stateHistory: SqueezeStateMarker[];
  discoveryNumber: number;
  priorDiscoveryDates: string[];
  atr14: number | null;
  atr14Prior: number | null;
  atrChangePct: number | null;
  priceBasis: string;
  overlayBasis: string;
}

export type StrategyReadinessStatus = "backtest_ready" | "diagnostic_only" | "blocked";

export interface StrategyReadinessEntry {
  key: string;
  name: string;
  market: "DSE" | "US";
  direction: "long" | "short" | "long_short";
  horizon: "scalp" | "swing" | "position";
  implementedStrategyKey: string | null;
  status: StrategyReadinessStatus;
  economicHypothesis: string;
  rationale: string;
  missingData: Array<{ key: string; description: string }>;
}

export interface StrategyReadinessBoard {
  market: "DSE" | "US";
  tenantId: string;
  generatedAt: string;
  entries: StrategyReadinessEntry[];
  methodology: string;
}

export interface ModelWindowMetrics {
  rows: number;
  dates: number;
  meanDailyRankIc: number | null;
  medianDailyRankIc: number | null;
  positiveIcDatesPct: number | null;
  trades: number;
  investedDates: number | null;
  abstentions: Record<string, number>;
  meanNetPct: number | null;
  meanStressedPct: number | null;
  annualizedNetPct: number | null;
  hitRatePct: number | null;
  sharpe: number | null;
  sharpeStandardError: number | null;
  sharpeLower95: number | null;
  years: number | null;
  meanEffectivePositions: number | null;
  maximumDrawdownPct: number | null;
}

export interface ModelSleeve {
  key: string;
  label: string;
  status: "evaluated" | "data_blocked";
  contract: {
    minimumPrice: number;
    minimumAdv: number;
    maximumAdv: number | null;
    allowedTrendRegimes: string[];
    allowedVolatilityRegimes: string[];
    bookNotional: number;
    maxPositions: number;
    minimumPositions: number;
    maxPositionWeight: number;
    maxAdvParticipation: number;
  };
  selectedPenalty: number | null;
  researchVerdict: string;
  blockers: string[];
  validation: ModelWindowMetrics | null;
  holdout: ModelWindowMetrics | null;
  momentumHoldout: ModelWindowMetrics | null;
}

export interface ModelSegmentedChallenger {
  key: string;
  version: string;
  trialCount: number;
  capSegmentationStatus: string;
  methodology: string;
  sleeves: ModelSleeve[];
}

export interface ModelHorizon {
  horizonSessions: number;
  specificationHash: string;
  selectedPenalty: number;
  researchVerdict: string;
  promotionStatus: string;
  promotionBlockers: string[];
  discovery: ModelWindowMetrics | null;
  validation: ModelWindowMetrics | null;
  holdout: ModelWindowMetrics | null;
  momentumHoldout: ModelWindowMetrics | null;
  topCoefficients: Array<{ feature: string; coefficient: number }>;
  segmentedChallenger: ModelSegmentedChallenger | null;
}

export interface ModelExperimentBoard {
  tenantId: string;
  market: "DSE" | "US";
  generatedAt: string;
  foundation: {
    snapshotId: string;
    asOfDate: string;
    policyKey: string;
    policyVersion: string;
    sourceMode: "point_in_time" | "current_projection";
    modelReady: boolean;
    candidateCount: number;
    eligibleCount: number;
    ineligibleCount: number;
    dataBlockedCount: number;
    modelEligibleCount: number;
    modelBlockers: Record<string, number>;
  } | null;
  experiment: {
    artifactSchemaVersion: string;
    artifactSha256: string;
    generatedAt: string;
    dataCutoff: string;
    dataScope: string;
    symbolsStreamed: number;
    boundedSample: boolean;
    status: "diagnostic" | "rejected";
    limitations: string[];
    horizons: ModelHorizon[];
  } | null;
  methodology: string;
}

export type DecisionCandidateState = "ready" | "manage" | "exit" | "blocked" | "closed";

export interface DecisionCandidate {
  id: string;
  portfolioId: string;
  portfolioName: string;
  strategyKey: string;
  strategyName: string;
  direction: "long" | "short";
  horizon: "swing" | "position";
  expectedHolding: string;
  code: string;
  company: string;
  capTier: string;
  state: DecisionCandidateState;
  evidenceMode: "forward" | "historical_replay";
  asOfDate: string;
  firstDiscoveredOn: string;
  isNew: boolean;
  discoveryPrice: number | null;
  asOfPrice: number | null;
  returnSinceDiscoveryPct: number | null;
  maxFavorablePct: number | null;
  maxAdversePct: number | null;
  sessionsSinceDiscovery: number;
  targetWeightPct: number;
  positionWeightPct: number;
  latestFillSide: "buy" | "sell" | null;
  latestFillPrice: number | null;
  latestFillDate: string | null;
  riskReferencePrice: number | null;
  invalidationPrice: number | null;
  planningObjectivePrice: number | null;
  planningRewardRisk: number | null;
  exitPolicy: string;
  headline: string;
  story: string;
  riskNotes: string[];
}

export interface DecisionBoard {
  workspaceId: string;
  tenantId: string;
  market: "DSE" | "US";
  generatedAt: string;
  selectedDate: string | null;
  latestDate: string | null;
  availableDates: string[];
  directionCapabilities: Array<{
    direction: "long" | "short";
    status: "active" | "blocked";
    reason: string;
  }>;
  candidates: DecisionCandidate[];
  methodology: string;
}

export interface DecisionCandidatePath {
  workspaceId: string;
  tenantId: string;
  market: "DSE" | "US";
  candidate: DecisionCandidate;
  points: Array<{
    date: string;
    close: number;
    volume: number;
    returnSinceDiscoveryPct: number | null;
  }>;
  events: DecisionEvent[];
  priceBasis: string;
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

function assertCatalystBoundary(
  calendar: CatalystCalendar,
  workspaceId: string,
): CatalystCalendar {
  const crossedBoundary =
    calendar.tenantId !== researchDeployment.tenant ||
    calendar.market !== researchDeployment.market ||
    calendar.workspaceId !== workspaceId;
  if (crossedBoundary) {
    throw new ResearchApiError(502, "The API returned research data outside this tenant boundary");
  }
  return calendar;
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

function assertOptionChainBoundary(
  chain: OptionChainPreview,
  workspaceId: string,
  ticker: string,
): OptionChainPreview {
  if (
    researchDeployment.market !== "US" ||
    chain.tenantId !== researchDeployment.tenant ||
    chain.market !== "US" ||
    chain.workspaceId !== workspaceId ||
    chain.code !== ticker
  ) {
    throw new ResearchApiError(502, "The API returned option data outside this tenant boundary");
  }
  return chain;
}

function assertConditionScanBoundary(
  scan: ConditionScan,
  workspaceId: string,
): ConditionScan {
  if (
    scan.tenantId !== researchDeployment.tenant ||
    scan.market !== researchDeployment.market ||
    scan.workspaceId !== workspaceId ||
    scan.items.some((item) => !item.ticker || item.ticker !== item.ticker.toUpperCase())
  ) {
    throw new ResearchApiError(
      502,
      "The API returned condition evidence outside this tenant boundary",
    );
  }
  return scan;
}

function assertConditionSubscriptionBoundary(
  subscription: ConditionSubscription,
  ticker: string,
): ConditionSubscription {
  if (
    subscription.tenantId !== researchDeployment.tenant ||
    subscription.market !== researchDeployment.market ||
    subscription.ticker !== ticker
  ) {
    throw new ResearchApiError(
      502,
      "The API returned an alert subscription outside this tenant boundary",
    );
  }
  return subscription;
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

function assertDecisionBoardBoundary(
  board: DecisionBoard,
  workspaceId: string,
): DecisionBoard {
  if (
    board.workspaceId !== workspaceId ||
    board.tenantId !== researchDeployment.tenant ||
    board.market !== researchDeployment.market
  ) {
    throw new ResearchApiError(502, "The API returned a decision archive outside this tenant boundary");
  }
  return board;
}

function assertDecisionPathBoundary(
  path: DecisionCandidatePath,
  workspaceId: string,
): DecisionCandidatePath {
  if (
    path.workspaceId !== workspaceId ||
    path.tenantId !== researchDeployment.tenant ||
    path.market !== researchDeployment.market
  ) {
    throw new ResearchApiError(502, "The API returned a decision path outside this tenant boundary");
  }
  return path;
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
  async conditionScan(
    workspaceId: string,
    filters: {
      conditionKey: ConditionKey;
      capTier?: string;
      newOnly?: boolean;
      limit?: number;
    },
    signal?: AbortSignal,
  ): Promise<ConditionScan> {
    const parameters = new URLSearchParams({ condition_key: filters.conditionKey });
    if (filters.capTier && filters.capTier !== "all") {
      parameters.set("cap_tier", filters.capTier);
    }
    if (filters.newOnly) parameters.set("new_only", "true");
    if (filters.limit) parameters.set("limit", String(filters.limit));
    const scan = await request<ConditionScan>(
      `/institutional-research/workspaces/${encodeURIComponent(workspaceId)}/condition-scan?${parameters.toString()}`,
      { signal },
    );
    return assertConditionScanBoundary(scan, workspaceId);
  },
  async setConditionSubscription(
    workspaceId: string,
    conditionKey: ConditionKey,
    ticker: string,
    enabled: boolean,
  ): Promise<ConditionSubscription> {
    const normalizedTicker = ticker.trim().toUpperCase();
    const subscription = await request<ConditionSubscription>(
      `/institutional-research/workspaces/${encodeURIComponent(workspaceId)}/condition-subscriptions/${encodeURIComponent(conditionKey)}/${encodeURIComponent(normalizedTicker)}`,
      { method: "PUT", body: JSON.stringify({ enabled }) },
    );
    return assertConditionSubscriptionBoundary(subscription, normalizedTicker);
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
  async optionChain(
    workspaceId: string,
    ticker: string,
    expiration?: string,
    signal?: AbortSignal,
  ): Promise<OptionChainPreview> {
    const normalizedTicker = ticker.trim().toUpperCase();
    const parameters = new URLSearchParams();
    if (expiration) parameters.set("expiration", expiration);
    const queryString = parameters.size ? `?${parameters.toString()}` : "";
    const chain = await request<OptionChainPreview>(
      `/institutional-research/workspaces/${encodeURIComponent(workspaceId)}/companies/${encodeURIComponent(normalizedTicker)}/options-chain${queryString}`,
      { signal },
    );
    return assertOptionChainBoundary(chain, workspaceId, normalizedTicker);
  },
  async catalystCalendar(
    workspaceId: string,
    filters: { horizonDays: number; code?: string },
    signal?: AbortSignal,
  ): Promise<CatalystCalendar> {
    const parameters = new URLSearchParams();
    parameters.set("horizon_days", String(filters.horizonDays));
    if (filters.code?.trim()) parameters.set("code", filters.code.trim().toUpperCase());
    const calendar = await request<CatalystCalendar>(
      `/institutional-research/workspaces/${encodeURIComponent(workspaceId)}/catalysts?${parameters.toString()}`,
      { signal },
    );
    return assertCatalystBoundary(calendar, workspaceId);
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
      strategy_key: BacktestStrategyKey;
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
  async investmentOperatingView(workspaceId: string): Promise<InvestmentOperatingView> {
    const view = await request<InvestmentOperatingView>(
      `/institutional-research/workspaces/${encodeURIComponent(workspaceId)}/investment-operating-view`,
    );
    if (
      view.workspaceId !== workspaceId ||
      view.tenantId !== researchDeployment.tenant ||
      view.market !== researchDeployment.market ||
      view.mandate.workspaceId !== workspaceId ||
      view.mandate.tenantId !== researchDeployment.tenant ||
      view.mandate.market !== researchDeployment.market ||
      view.trials.some((trial) =>
        trial.workspaceId !== workspaceId ||
        trial.tenantId !== researchDeployment.tenant ||
        trial.market !== researchDeployment.market
      ) ||
      view.portfolios.some((portfolio) =>
        portfolio.mandate.workspaceId !== workspaceId ||
        portfolio.mandate.tenantId !== researchDeployment.tenant ||
        portfolio.mandate.market !== researchDeployment.market ||
        !Number.isFinite(portfolio.risk.largestPositionPct) ||
        !Number.isFinite(portfolio.risk.largestSectorPct) ||
        !Number.isFinite(portfolio.risk.effectivePositions) ||
        portfolio.risk.stressScenarios.some(
          (scenario) => !Number.isFinite(scenario.estimatedLossPct),
        ) ||
        portfolio.attribution.components.some(
          (component) => component.contributionPct !== null &&
            !Number.isFinite(component.contributionPct),
        )
      )
    ) {
      throw new ResearchApiError(502, "The API returned investment data outside this tenant boundary");
    }
    return view;
  },
  async squeezeMonitor(asOf?: string): Promise<SqueezeMonitor> {
    const parameters = new URLSearchParams();
    if (asOf) parameters.set("as_of", asOf);
    const query = parameters.size ? `?${parameters.toString()}` : "";
    const monitor = await request<SqueezeMonitor>(
      `/institutional-research/squeeze-monitor${query}`,
    );
    if (
      monitor.tenantId !== researchDeployment.tenant ||
      monitor.market !== researchDeployment.market
    ) {
      throw new ResearchApiError(502, "The API returned squeeze data outside this tenant boundary");
    }
    return monitor;
  },
  async squeezePath(family: string, code: string, asOf?: string): Promise<SqueezePath> {
    const parameters = new URLSearchParams();
    if (asOf) parameters.set("as_of", asOf);
    const query = parameters.size ? `?${parameters.toString()}` : "";
    const path = await request<SqueezePath>(
      `/institutional-research/squeeze-monitor/${encodeURIComponent(family)}/${encodeURIComponent(code.toUpperCase())}${query}`,
    );
    if (
      path.tenantId !== researchDeployment.tenant ||
      path.market !== researchDeployment.market
    ) {
      throw new ResearchApiError(502, "The API returned squeeze data outside this tenant boundary");
    }
    return path;
  },
  async strategyReadiness(): Promise<StrategyReadinessBoard> {
    const board = await request<StrategyReadinessBoard>(
      "/institutional-research/strategy-readiness",
    );
    if (
      board.tenantId !== researchDeployment.tenant ||
      board.market !== researchDeployment.market
    ) {
      throw new ResearchApiError(502, "The API returned readiness data outside this tenant boundary");
    }
    return board;
  },
  async modelExperiment(): Promise<ModelExperimentBoard> {
    const board = await request<ModelExperimentBoard>(
      "/institutional-research/model-experiments/latest",
    );
    if (
      board.tenantId !== researchDeployment.tenant ||
      board.market !== researchDeployment.market
    ) {
      throw new ResearchApiError(502, "The API returned a model audit outside this tenant boundary");
    }
    return board;
  },
  async decisionBoard(workspaceId: string, asOf?: string): Promise<DecisionBoard> {
    const parameters = new URLSearchParams();
    if (asOf) parameters.set("as_of", asOf);
    const query = parameters.size ? `?${parameters.toString()}` : "";
    return assertDecisionBoardBoundary(
      await request<DecisionBoard>(
        `/institutional-research/workspaces/${encodeURIComponent(workspaceId)}/decision-board${query}`,
      ),
      workspaceId,
    );
  },
  async decisionCandidatePath(
    workspaceId: string,
    portfolioId: string,
    code: string,
    asOf?: string,
  ): Promise<DecisionCandidatePath> {
    const parameters = new URLSearchParams();
    if (asOf) parameters.set("as_of", asOf);
    const query = parameters.size ? `?${parameters.toString()}` : "";
    return assertDecisionPathBoundary(
      await request<DecisionCandidatePath>(
        `/institutional-research/workspaces/${encodeURIComponent(workspaceId)}/decision-board/${encodeURIComponent(portfolioId)}/${encodeURIComponent(code.toUpperCase())}${query}`,
      ),
      workspaceId,
    );
  },
  async configureInvestmentMandate(
    workspaceId: string,
    payload: InvestmentMandateInput,
  ): Promise<InvestmentMandate> {
    const mandate = await request<InvestmentMandate>(
      `/institutional-research/workspaces/${encodeURIComponent(workspaceId)}/investment-mandate`,
      { method: "PUT", body: JSON.stringify(payload) },
    );
    if (
      mandate.workspaceId !== workspaceId ||
      mandate.tenantId !== researchDeployment.tenant ||
      mandate.market !== researchDeployment.market
    ) {
      throw new ResearchApiError(502, "The API returned a mandate outside this tenant boundary");
    }
    return mandate;
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
