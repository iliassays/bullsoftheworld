import type { ResearchCandidate, ResearchMarket } from "../research-queue/model";

export interface DossierPricePoint {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  benchmarkClose: number | null;
}

export type ResearchConditionKey =
  | "trend_alignment"
  | "participation_expansion"
  | "controlled_pullback_context";

export type ResearchConditionState = "observed" | "not_observed" | "unavailable";

export interface DossierOverlaySeries {
  key: "ema20" | "ema50";
  label: string;
  points: Array<{ date: string; value: number }>;
}

export interface ResearchConditionCheck {
  factKey: string;
  label: string;
  observed: number | null;
  expected: string;
  unit: "percent" | "multiple";
  passed: boolean | null;
}

export interface ResearchConditionTransition {
  date: string;
  close: number;
  sequence: number;
}

export interface ResearchConditionEvaluation {
  key: ResearchConditionKey;
  version: string;
  title: string;
  shortLabel: string;
  category: string;
  state: ResearchConditionState;
  summary: string;
  whyItMatters: string;
  limitation: string;
  checks: ResearchConditionCheck[];
  transitions: ResearchConditionTransition[];
}

export interface ResearchConditionWorkbench {
  methodologyVersion: string;
  timeframe: "1d";
  asOfDate: string | null;
  historyStartDate: string | null;
  disclaimer: string;
  overlays: DossierOverlaySeries[];
  conditions: ResearchConditionEvaluation[];
}

export interface ReportedOwnershipCategory {
  key: "sponsor_director" | "government" | "institutional" | "foreign" | "public";
  label: string;
  valuePct: number;
  changePp: number | null;
}

export interface ResearchCompanyDossier {
  tenantId: string;
  market: ResearchMarket;
  workspaceId: string;
  generatedAt: string;
  knowledgeCutoffAt: string;
  candidate: ResearchCandidate;
  marketData: {
    asOfDate: string;
    benchmarkCode: string;
    marketCapMn: number | null;
    freeFloatCapMn: number | null;
    week52High: number | null;
    week52Low: number | null;
    nearestSupport: number | null;
    nearestResistance: number | null;
    averageVolume20: number | null;
    relativeVolume: number | null;
    cmf20: number | null;
    obvSlope: number | null;
    rsi14: number | null;
    volatilityPct: number | null;
  };
  fundamentals: {
    peRatio: number | null;
    pbRatio: number | null;
    dividendYieldPct: number | null;
    roePct: number | null;
    epsGrowthYoyPct: number | null;
    peVsSector: number | null;
  };
  priceHistory: DossierPricePoint[];
  conditionWorkbench: ResearchConditionWorkbench;
  reportedOwnership: {
    asOfDate: string;
    previousAsOfDate: string | null;
    compositionTotalPct: number;
    categories: ReportedOwnershipCategory[];
    interpretation: string;
    limitations: string[];
  } | null;
  institutionalDisclosure: {
    reportDate: string;
    publicBy: string;
    managersCount: number;
    totalValueUsd: number;
    netShareChange: number | null;
    netChangePct: number | null;
    addingManagers: number;
    reducingManagers: number;
    unchangedManagers: number;
    netBreadthPct: number | null;
    sourceUrl: string;
    interpretation: string;
    limitations: string[];
  } | null;
  shortActivity: {
    asOfDate: string;
    shortMarkedSharePct: number;
    average20Pct: number | null;
    deviationPp: number | null;
    activityVs20x: number | null;
    baselineSessions: number;
    sourceUrl: string;
    interpretation: string;
    limitations: string[];
  } | null;
  dataQualityNotes: string[];
}
