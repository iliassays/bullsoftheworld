import { researchDeployment } from "../../app/deployment";
import type {
  ConditionCalibration,
  ConditionCheck,
  ConditionKey,
  ConditionScan,
  ConditionScanItem,
} from "./model";

const latest = "2026-08-10";

const checks: Record<ConditionKey, ConditionCheck[]> = {
  trend_alignment: [
    { factKey: "close_vs_ema20_pct", label: "Close above EMA20", observed: 4.8, expected: "> 0%", unit: "percent", passed: true },
    { factKey: "ema20_vs_ema50_pct", label: "EMA20 above EMA50", observed: 3.1, expected: "> 0%", unit: "percent", passed: true },
    { factKey: "ema20_slope_5_pct", label: "EMA20 rising over 5 sessions", observed: 1.7, expected: "> 0%", unit: "percent", passed: true },
    { factKey: "ema50_slope_10_pct", label: "EMA50 rising over 10 sessions", observed: 1.1, expected: "> 0%", unit: "percent", passed: true },
  ],
  participation_expansion: [
    { factKey: "relative_volume_20", label: "Volume versus prior 20 sessions", observed: 2.35, expected: ">= 1.50x", unit: "multiple", passed: true },
    { factKey: "daily_return_pct", label: "Completed-session price change", observed: 3.4, expected: "> 0%", unit: "percent", passed: true },
    { factKey: "close_vs_ema20_pct", label: "Close relative to EMA20", observed: 5.2, expected: ">= 0%", unit: "percent", passed: true },
  ],
  controlled_pullback_context: [
    { factKey: "ema20_vs_ema50_pct", label: "EMA20 above EMA50", observed: 4.1, expected: "> 0%", unit: "percent", passed: true },
    { factKey: "ema20_slope_5_pct", label: "EMA20 rising over 5 sessions", observed: 0.8, expected: "> 0%", unit: "percent", passed: true },
    { factKey: "close_vs_ema20_pct", label: "Close near EMA20", observed: -1.2, expected: "-3.00% to +2.00%", unit: "percent", passed: true },
    { factKey: "close_vs_ema50_pct", label: "Close above EMA50", observed: 2.9, expected: "> 0%", unit: "percent", passed: true },
    { factKey: "relative_volume_20", label: "Volume remains controlled", observed: 0.74, expected: "<= 1.20x", unit: "multiple", passed: true },
  ],
};

const marketNames = researchDeployment.market === "DSE"
  ? [
      ["BRACBANK", "BRAC Bank PLC", "Financials", "large", 64.8, 0.0],
      ["SQURPHARMA", "Square Pharmaceuticals PLC", "Pharmaceuticals", "large", 229.4, 1.6],
      ["GP", "Grameenphone Ltd.", "Telecommunications", "large", 317.6, -0.4],
      ["CITYBANK", "The City Bank PLC", "Financials", "mid", 31.7, 5.1],
    ] as const
  : [
      ["MSFT", "Microsoft Corporation", "Technology", "mega", 526.3, 0.0],
      ["PLTR", "Palantir Technologies Inc.", "Software", "large", 185.4, 8.2],
      ["AMD", "Advanced Micro Devices, Inc.", "Semiconductors", "large", 176.7, -1.1],
      ["RKLB", "Rocket Lab Corporation", "Aerospace & Defense", "mid", 52.8, 6.7],
    ] as const;

function itemsFor(conditionKey: ConditionKey): ConditionScanItem[] {
  return marketNames.map(([ticker, company, sector, capTier, price, change], index) => ({
    ticker,
    company,
    sector,
    capTier,
    observedOn: index === 0 ? latest : `2026-08-0${Math.max(2, 9 - index)}`,
    latestSessionDate: latest,
    referenceClose: price / (1 + change / 100),
    latestClose: price,
    closeReturnSinceObservationPct: change,
    averageDailyValueMn: index === 3 ? 12.4 : 180.2 - index * 36,
    evidenceMode: index === 0 ? "forward" : "reconstructed",
    isNew: index === 0,
    subscribed: index === 1,
    checks: checks[conditionKey],
  }));
}

function calibrations(conditionKey: ConditionKey): ConditionCalibration[] {
  const statistics = {
    1: { median: 0.34, positive: 52.1, excess: 0.08, favorable: 1.9, adverse: -1.5 },
    5: { median: 1.18, positive: 55.4, excess: 0.41, favorable: 4.8, adverse: -3.2 },
    20: { median: 2.86, positive: 58.2, excess: 0.72, favorable: 9.2, adverse: -6.4 },
    60: { median: 4.22, positive: 60.1, excess: 0.94, favorable: 16.8, adverse: -11.2 },
  } as const;
  return ([1, 5, 20, 60] as const).map((horizon, index) => {
    const result = statistics[horizon];
    return {
      conditionKey,
      conditionVersion: "1.0.0",
      evidenceMode: "reconstructed" as const,
      horizonSessions: horizon,
      asOfDate: latest,
      historyStartDate: "2025-06-02",
      observations: 684 - index * 42,
      matured: 675 - index * 55,
      pending: 9 + index * 13,
      medianReturnPct: result.median,
      positiveRatePct: result.positive,
      medianExcessReturnPct: result.excess,
      benchmarkObservations: 675 - index * 55,
      averageMaxFavorablePct: result.favorable,
      averageMaxAdversePct: result.adverse,
      universeSize: researchDeployment.market === "DSE" ? 286 : 7320,
      pointInTimeComplete: false,
      warningText: "Rolling reconstructed diagnostic; not strategy performance.",
    };
  });
}

const definitions = {
  trend_alignment: {
    key: "trend_alignment" as const,
    version: "1.0.0",
    title: "Trend alignment",
    category: "trend",
    whyItMatters: "A rising 20-session trend above a rising 50-session trend describes persistent direction rather than a one-session jump.",
    limitation: "Moving averages react after price and can remain aligned late in a move.",
  },
  participation_expansion: {
    key: "participation_expansion" as const,
    version: "1.0.0",
    title: "Participation expansion",
    category: "volume",
    whyItMatters: "Price strength with volume above the prior 20-session pace is broader evidence than price alone.",
    limitation: "Volume can reflect distribution, news, rebalancing, or forced activity.",
  },
  controlled_pullback_context: {
    key: "controlled_pullback_context" as const,
    version: "1.0.0",
    title: "Controlled pullback context",
    category: "trend context",
    whyItMatters: "A quiet return toward EMA20 while EMA50 remains intact can focus follow-up research on orderly consolidation.",
    limitation: "This daily-bar context is not an intraday entry rule.",
  },
};

export function previewConditionScan(
  workspaceId: string,
  conditionKey: ConditionKey,
): ConditionScan {
  const items = itemsFor(conditionKey);
  return {
    tenantId: researchDeployment.tenant,
    market: researchDeployment.market,
    workspaceId,
    generatedAt: "2026-08-11T06:30:00Z",
    latestSessionDate: latest,
    methodologyVersion: "research-conditions-v1",
    definition: definitions[conditionKey],
    observedCount: items.length,
    newCount: items.filter((item) => item.isNew).length,
    returnedCount: items.length,
    items,
    calibrations: calibrations(conditionKey),
    warnings: [
      "Observed means the completed-session checks are present; it is not a trade signal, probability estimate, or order.",
      "Reconstructed outcomes use the current active universe and are diagnostic only.",
    ],
  };
}
