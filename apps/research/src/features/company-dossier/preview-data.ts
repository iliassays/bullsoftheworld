import { researchDeployment } from "../../app/deployment";
import { demoQueueSnapshot } from "../research-queue/preview-data";
import type { ResearchCompanyDossier } from "./model";

export function previewDossier(workspaceId: string, ticker: string): ResearchCompanyDossier {
  const candidate = demoQueueSnapshot.candidates.find(
    (item) => item.market === researchDeployment.market && item.ticker === ticker.toUpperCase(),
  );
  if (!candidate) throw new Error(`No preview dossier exists for ${ticker}`);

  const start = new Date("2026-06-30T00:00:00Z");
  const priceHistory = candidate.sparkline.map((close, index) => {
    const date = new Date(start);
    date.setUTCDate(start.getUTCDate() + index);
    return {
      date: date.toISOString().slice(0, 10),
      close,
      volume: 150_000 + index * 18_500,
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
      marketCapMn: isDse ? 8_720 : 142,
      freeFloatCapMn: isDse ? 3_410 : 77,
      week52High: candidate.price * 1.28,
      week52Low: candidate.price * 0.61,
      nearestSupport: candidate.price * 0.92,
      nearestResistance: candidate.price * 1.08,
      averageVolume20: 320_000,
      relativeVolume: 1.34,
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
