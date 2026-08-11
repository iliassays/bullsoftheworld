import { researchDeployment } from "../../app/deployment";
import { demoQueueSnapshot } from "../research-queue/preview-data";
import type { ResearchCompanyDossier } from "./model";

function previewEma(
  points: Array<{ date: string; close: number }>,
  period: number,
): Array<{ date: string; value: number }> {
  if (points.length < period) return [];
  const multiplier = 2 / (period + 1);
  let value = points.slice(0, period).reduce((sum, point) => sum + point.close, 0) / period;
  const output = [{ date: points[period - 1]!.date, value }];
  for (let index = period; index < points.length; index += 1) {
    value = (points[index]!.close - value) * multiplier + value;
    output.push({ date: points[index]!.date, value });
  }
  return output;
}

export function previewDossier(workspaceId: string, ticker: string): ResearchCompanyDossier {
  const candidate = demoQueueSnapshot.candidates.find(
    (item) => item.market === researchDeployment.market && item.ticker === ticker.toUpperCase(),
  );
  if (!candidate) throw new Error(`No preview dossier exists for ${ticker}`);

  const start = new Date("2026-06-30T00:00:00Z");
  const sessionDates: string[] = [];
  for (
    const date = new Date(start);
    sessionDates.length < candidate.sparkline.length;
    date.setUTCDate(date.getUTCDate() + 1)
  ) {
    const weekday = date.getUTCDay();
    if (weekday !== 0 && weekday !== 6) {
      sessionDates.push(date.toISOString().slice(0, 10));
    }
  }
  const priceHistory = candidate.sparkline.map((close, index) => {
    const open = index === 0 ? close * 0.985 : candidate.sparkline[index - 1]!;
    return {
      date: sessionDates[index]!,
      open,
      high: Math.max(open, close) * 1.018,
      low: Math.min(open, close) * 0.982,
      close,
      volume: 150_000 + index * 18_500,
      benchmarkClose: 100 + index * 0.45,
    };
  });

  const isDse = candidate.market === "DSE";
  return {
    tenantId: researchDeployment.tenant,
    market: researchDeployment.market,
    workspaceId,
    generatedAt: demoQueueSnapshot.generatedAt,
    knowledgeCutoffAt: candidate.evidence.knownAt,
    candidate,
    marketData: {
      asOfDate: candidate.evidence.knownAt.slice(0, 10),
      benchmarkCode: isDse ? "DSEX" : "SPY",
      marketCapMn: isDse ? 8_720 : 142,
      freeFloatCapMn: isDse ? 3_410 : 77,
      week52High: candidate.price * 1.28,
      week52Low: candidate.price * 0.61,
      nearestSupport: candidate.price * 0.92,
      nearestResistance: candidate.price * 1.08,
      averageVolume20: 320_000,
      relativeVolume: 1.34,
      cmf20: 0.14,
      obvSlope: 0.22,
      rsi14: 61,
      volatilityPct: isDse ? 43 : 78,
    },
    fundamentals: {
      peRatio: 14.2,
      pbRatio: 1.8,
      dividendYieldPct: isDse ? 4.1 : null,
      roePct: 17.4,
      epsGrowthYoyPct: 12.8,
      peVsSector: 0.82,
    },
    priceHistory,
    conditionWorkbench: {
      methodologyVersion: "research-conditions-v1",
      timeframe: "1d",
      asOfDate: priceHistory.at(-1)?.date ?? null,
      historyStartDate: priceHistory.at(0)?.date ?? null,
      disclaimer:
        "Completed-session research conditions only. An observation is not a recommendation, probability estimate, strategy qualification, target, or order.",
      overlays: [
        { key: "ema20", label: "EMA20", points: previewEma(priceHistory, 20) },
        { key: "ema50", label: "EMA50", points: previewEma(priceHistory, 50) },
      ],
      conditions: [
        {
          key: "trend_alignment",
          version: "1.0.0",
          title: "Trend alignment",
          shortLabel: "T",
          category: "trend",
          state: "observed",
          summary: "All 4 completed-session checks are present at this cutoff.",
          whyItMatters: "Rising short and intermediate trends describe persistence rather than a one-session jump.",
          limitation: "Moving averages react after price and do not estimate future return.",
          checks: [
            { factKey: "close_vs_ema20_pct", label: "Close above EMA20", observed: 2.4, expected: "> 0%", unit: "percent", passed: true },
            { factKey: "ema20_vs_ema50_pct", label: "EMA20 above EMA50", observed: 3.1, expected: "> 0%", unit: "percent", passed: true },
            { factKey: "ema20_slope_5_pct", label: "EMA20 rising over 5 sessions", observed: 1.2, expected: "> 0%", unit: "percent", passed: true },
            { factKey: "ema50_slope_10_pct", label: "EMA50 rising over 10 sessions", observed: 1.5, expected: "> 0%", unit: "percent", passed: true },
          ],
          transitions: priceHistory.length ? [{ date: priceHistory[Math.max(0, priceHistory.length - 4)]!.date, close: priceHistory[Math.max(0, priceHistory.length - 4)]!.close, sequence: 1 }] : [],
        },
        {
          key: "participation_expansion",
          version: "1.0.0",
          title: "Participation expansion",
          shortLabel: "V",
          category: "volume",
          state: "not_observed",
          summary: "2 of 3 checks are present; the full condition is not observed.",
          whyItMatters: "Price strength with materially higher participation is broader evidence than price alone.",
          limitation: "Volume does not identify an institution or prove accumulation.",
          checks: [
            { factKey: "relative_volume_20", label: "Volume versus prior 20 sessions", observed: 1.34, expected: ">= 1.50x", unit: "multiple", passed: false },
            { factKey: "daily_return_pct", label: "Completed-session price change", observed: 1.1, expected: "> 0%", unit: "percent", passed: true },
            { factKey: "close_vs_ema20_pct", label: "Close relative to EMA20", observed: 2.4, expected: ">= 0%", unit: "percent", passed: true },
          ],
          transitions: [],
        },
        {
          key: "controlled_pullback_context",
          version: "1.0.0",
          title: "Controlled pullback context",
          shortLabel: "P",
          category: "trend context",
          state: "not_observed",
          summary: "4 of 5 checks are present; the full condition is not observed.",
          whyItMatters: "An orderly return toward the short trend can focus consolidation research.",
          limitation: "This daily proxy is not an intraday pullback strategy or entry rule.",
          checks: [
            { factKey: "ema20_vs_ema50_pct", label: "EMA20 above EMA50", observed: 3.1, expected: "> 0%", unit: "percent", passed: true },
            { factKey: "ema20_slope_5_pct", label: "EMA20 rising over 5 sessions", observed: 1.2, expected: "> 0%", unit: "percent", passed: true },
            { factKey: "close_vs_ema20_pct", label: "Close near EMA20", observed: 2.4, expected: "-3.00% to +2.00%", unit: "percent", passed: false },
            { factKey: "close_vs_ema50_pct", label: "Close above EMA50", observed: 5.6, expected: "> 0%", unit: "percent", passed: true },
            { factKey: "relative_volume_20", label: "Volume remains controlled", observed: 1.34, expected: "<= 1.20x", unit: "multiple", passed: false },
          ],
          transitions: [],
        },
      ],
    },
    reportedOwnership: isDse
      ? {
          asOfDate: "2026-06-30",
          previousAsOfDate: "2026-05-31",
          compositionTotalPct: 100,
          categories: [
            { key: "sponsor_director", label: "Sponsor / director", valuePct: 30, changePp: 0 },
            { key: "government", label: "Government", valuePct: 10, changePp: 0 },
            { key: "institutional", label: "Institutional", valuePct: 25, changePp: 1.5 },
            { key: "foreign", label: "Foreign", valuePct: 5, changePp: -0.5 },
            { key: "public", label: "Public", valuePct: 30, changePp: -1 },
          ],
          interpretation:
            "This is the issuer's reported ownership composition. Changes compare disclosure dates and do not prove session-level trading.",
          limitations: [
            "Disclosure categories are periodic, not observed in real time.",
            "The institutional category does not identify individual investors.",
          ],
        }
      : null,
    institutionalDisclosure: isDse
      ? null
      : {
          reportDate: "2026-03-31",
          publicBy: "2026-05-15",
          managersCount: 18,
          totalValueUsd: 12_400_000,
          netShareChange: 214_000,
          netChangePct: 8.7,
          addingManagers: 7,
          reducingManagers: 3,
          unchangedManagers: 8,
          netBreadthPct: 40,
          sourceUrl: "https://www.sec.gov/edgar/search/",
          interpretation:
            "Net breadth compares managers reporting additions with managers reporting reductions for the quarter. It is not live fund flow.",
          limitations: [
            "Form 13F reports quarter-end positions and can be filed up to 45 days later.",
            "It omits many shorts, derivatives, and intra-quarter trades.",
          ],
        },
    shortActivity: isDse
      ? null
      : {
          asOfDate: "2026-07-14",
          shortMarkedSharePct: 57.4,
          average20Pct: 48.2,
          deviationPp: 9.2,
          activityVs20x: 1.3,
          baselineSessions: 20,
          sourceUrl: "https://www.finra.org/finra-data/browse-catalog/short-sale-volume-data",
          interpretation:
            "FINRA short-marked activity is above this security's recent baseline. It does not establish bearish positioning.",
          limitations: [
            "Daily short-sale volume is not short interest.",
            "It includes market-making and hedging activity.",
          ],
        },
    dataQualityNotes: ["Preview values are illustrative and are not a production research record."],
  };
}
