export type FactorKey = "quality" | "value" | "momentum" | "risk";

export interface MetricGuidance {
  definition: string;
  reference: string;
}

export const METRIC_GUIDANCE = {
  priority: {
    definition: "Ranks where analyst attention is most useful. It is not an expected-return score.",
    reference: "Higher means research sooner, not buy sooner.",
  },
  evidenceCoverage: {
    definition: "Share of the market-specific evidence requirements currently present and usable.",
    reference: "Atlas needs at least 60% plus official evidence to qualify a research case.",
  },
  capacity: {
    definition: "Estimated position size that could be exited within the stated sessions at the bounded participation rate.",
    reference: "A research capacity estimate, not guaranteed executable size.",
  },
  relativeVolume: {
    definition: "Completed-session volume divided by the stock's average volume over the prior 20 sessions.",
    reference: "1.00x is normal; below 0.80x is weak confirmation for a constructive trend.",
  },
  cmfObv: {
    definition: "CMF estimates buying or selling pressure; OBV slope tracks whether volume flow is rising or falling.",
    reference: "Zero is neutral. CMF at or below -0.05 with negative OBV is a distribution warning.",
  },
  rsi: {
    definition: "RSI measures the speed and persistence of recent price movement on a 0-100 scale.",
    reference: "Atlas treats 75 or higher as elevated entry-timing and crowding risk, not an automatic sell.",
  },
  volatility: {
    definition: "Annualized variability of completed-session returns.",
    reference: "Compare with the same market and capitalization tier; lower is not automatically better.",
  },
  pe: {
    definition: "Price divided by normalized positive earnings per share.",
    reference: "Compare with the sector, growth and earnings durability; a low P/E can be a value trap.",
  },
  pb: {
    definition: "Market price divided by reported book value per share.",
    reference: "Most useful within the same sector; asset-heavy and asset-light companies are not comparable.",
  },
  roe: {
    definition: "Normalized profit generated relative to reported shareholder equity.",
    reference: "Atlas fundamental support requires ROE at least 10% together with EPS growth at least 10%.",
  },
  epsGrowth: {
    definition: "Year-over-year change in normalized earnings per share.",
    reference: "10% or more supports the case with ROE; 80% or more requires a base-effect and cash-flow check.",
  },
  dividendYield: {
    definition: "Trailing cash dividend relative to the current share price.",
    reference: "Judge against payout durability, cash flow and local interest rates; there is no universal ideal yield.",
  },
  peVsSector: {
    definition: "The company's normalized positive-earnings P/E divided by its sector median P/E.",
    reference: "1.00x is the sector median; 0.85x or less supports value, while 1.25x or more is a premium.",
  },
} satisfies Record<string, MetricGuidance>;

export const FACTOR_GUIDANCE: Record<FactorKey, MetricGuidance> = {
  quality: {
    definition: "Combines profitability, earnings direction and whether positive earnings are observed.",
    reference: "50 is the model midpoint; higher is stronger, but the underlying facts decide the thesis.",
  },
  value: {
    definition: "Combines sector-relative P/E, absolute P/E, P/B and dividend yield where available.",
    reference: "50 is the model midpoint; higher means cheaper on available inputs, not a price target.",
  },
  momentum: {
    definition: "Combines multi-horizon trend, moving-average position and RSI with an extension penalty.",
    reference: "50 is the model midpoint; stronger momentum can still carry crowding risk at RSI 75+.",
  },
  risk: {
    definition: "Combines liquidity, volatility, capitalization and evidence gaps. Unlike other factors, lower is better.",
    reference: "Below 75 is required for qualification; 85 or higher is a hard research rejection.",
  },
};

export function factorReading(key: FactorKey, value: number): string {
  if (key === "risk") {
    if (value >= 85) return "Hard rejection band";
    if (value >= 75) return "Blocks qualification";
    if (value >= 50) return "Elevated burden";
    return "Lower burden";
  }
  if (value >= 65) return "Stronger than midpoint";
  if (value >= 45) return "Near model midpoint";
  return "Limited support";
}
