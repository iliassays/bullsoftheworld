export type ResearchMarket = "DSE" | "US";
export type QueueStatus = "new_evidence" | "needs_review" | "monitoring";
export type QueueStatusFilter = "all" | QueueStatus;
export type CapTier = "mega" | "large" | "mid" | "small" | "micro" | "penny" | "unclassified";
export type CapTierFilter = "all" | CapTier;
export type EvidenceFreshness = "fresh" | "aging" | "gap";
export type CatalystConfidence = "confirmed" | "inferred";

export interface ResearchFactorSet {
  quality: number;
  value: number;
  momentum: number;
  risk: number;
}

export interface ResearchDimension {
  value: number;
  confidence: number;
  explanation: string;
  inputs: Record<string, number | boolean | string | null>;
}

export interface ResearchEvidenceItem {
  id: string;
  source: string;
  title: string;
  publishedAt: string;
  purpose: "supporting" | "counter" | "context";
  confidence: "primary" | "derived";
  url?: string | null;
}

export interface ResearchEvidenceRequirement {
  key: string;
  label: string;
  present: boolean;
  asOf: string | null;
}

export interface ResearchScenario {
  id: "bear" | "base" | "bull";
  value: number;
  returnPct: number;
  premise: string;
}

export interface ResearchCandidate {
  id: string;
  market: ResearchMarket;
  ticker: string;
  company: string;
  sector: string;
  capTier: CapTier;
  currency: "BDT" | "USD";
  price: number;
  dailyChangePct: number | null;
  priority: number;
  priorityExplanation?: string;
  methodologyVersion?: string;
  status: QueueStatus;
  owner: string | null;
  queueReason: string;
  keyChange: string;
  thesisSummary: string;
  invalidation: string;
  catalyst: {
    label: string;
    window: string;
    daysAway: number;
    confidence: CatalystConfidence;
  } | null;
  factors: ResearchFactorSet;
  factorDetails?: Record<keyof ResearchFactorSet | "novelty", ResearchDimension>;
  evidence: {
    freshness: EvidenceFreshness;
    sourceCount: number;
    counterCount: number | null;
    coveragePct: number;
    knownAt: string;
    requirements?: ResearchEvidenceRequirement[];
    items: ResearchEvidenceItem[];
  };
  liquidity: {
    averageDailyValue: string;
    capacity: string;
    exitDays: number;
    basis?: string;
  };
  flags: string[];
  scenarios: ResearchScenario[];
  sparkline: number[];
}

export interface ResearchQueueSnapshot {
  tenantId?: string;
  market?: ResearchMarket;
  workspaceId?: string;
  generatedAt: string;
  knowledgeCutoffAt: string;
  universeCount: number;
  eligibleCount: number;
  returnedCount: number;
  isTruncated: boolean;
  candidates: ResearchCandidate[];
}

export interface QueueFilters {
  status: QueueStatusFilter;
  capTier: CapTierFilter;
  query: string;
}

export interface QueueSummary {
  total: number;
  newEvidence: number;
  needsReview: number;
  catalystSevenDays: number;
  evidenceGaps: number;
}

export function filterResearchQueue(
  candidates: readonly ResearchCandidate[],
  filters: QueueFilters,
): ResearchCandidate[] {
  const query = filters.query.trim().toLocaleLowerCase();
  return candidates.filter((candidate) => {
    if (filters.status !== "all" && candidate.status !== filters.status) return false;
    if (filters.capTier !== "all" && candidate.capTier !== filters.capTier) return false;
    if (!query) return true;
    return [candidate.ticker, candidate.company, candidate.sector, candidate.queueReason]
      .join(" ")
      .toLocaleLowerCase()
      .includes(query);
  });
}

export function summarizeResearchQueue(candidates: readonly ResearchCandidate[]): QueueSummary {
  return {
    total: candidates.length,
    newEvidence: candidates.filter((candidate) => candidate.status === "new_evidence").length,
    needsReview: candidates.filter((candidate) => candidate.status === "needs_review").length,
    catalystSevenDays: candidates.filter(
      (candidate) => candidate.catalyst !== null && candidate.catalyst.daysAway <= 7,
    ).length,
    evidenceGaps: candidates.filter((candidate) => candidate.evidence.freshness === "gap").length,
  };
}
