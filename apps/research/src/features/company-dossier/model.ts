import type { ResearchCandidate, ResearchMarket } from "../research-queue/model";

export interface DossierPricePoint {
  date: string;
  close: number;
  volume: number;
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
