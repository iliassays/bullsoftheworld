export interface StrategySelectionGuide {
  universe: string;
  entry: string;
  ranking: string;
  sizing: string;
}

export function strategySelectionGuide(
  strategyKey: string,
  universeSize: number | null,
): StrategySelectionGuide {
  const universe = universeSize === null ? "the registered liquid universe" : `${universeSize} active liquid securities`;

  if (strategyKey === "dse_reversal_v1") {
    return {
      universe: `${universe}, ranked by completed-session traded value`,
      entry: "At least 12% below the 126-session peak, positive five-session return, RSI at or below 58, 20/60-session volume ratio at or above 0.90, and at least BDT 2m average daily value",
      ranking: "Passing recoveries rank by drawdown depth, five-session recovery, and volume confirmation; queue urgency is not used",
      sizing: "Target volatility, 12% position cap, 30% sector cap, 85% gross exposure cap, liquidity, fees, and slippage",
    };
  }

  if (strategyKey === "us_breakout_v1") {
    return {
      universe: `${universe}, ranked by completed-session traded value`,
      entry: "Close above the 50-day average, 50-day above 200-day, positive 63-session momentum, volume ratio at or above 0.90, and no more than 25% above the 50-day average",
      ranking: "Passing trends rank by 63-session momentum, proximity to the 20-session high, volume confirmation, and volatility; queue urgency is not used",
      sizing: "Target volatility, 10% position cap, 25% sector cap, 90% gross exposure cap, liquidity, fees, and slippage",
    };
  }

  if (strategyKey === "us_activist_13d_v1") {
    return {
      universe: "New Schedule 13D disclosures by a frozen, repeat-activist roster",
      entry: "The filing must be public, mapped to the correct security, and pass as-of spread and market-cap gates",
      ranking: "Roster qualification is the mechanism; campaign events rank ahead of unqualified aggregate 13D activity",
      sizing: "1/N event book, 5% signal cap, 20-name ceiling, next-close fills, staged time exits, and immediate thesis-break exits",
    };
  }

  if (strategyKey === "us_insider_cluster_v1") {
    return {
      universe: "Open-market Form 4 purchases with a usable SEC acceptance timestamp",
      entry: "P-code, non-10b5-1, and opportunistic classification using only owner history public at that filing",
      ranking: "Multi-insider clusters and officer/director participation rank above single purchases",
      sizing: "1/N event book, 5% signal cap, 20-name ceiling, next-close fills, measured costs, and a hard time stop",
    };
  }

  if (strategyKey === "us_forced_seller_v1") {
    return {
      universe: "Completed spin-offs, post-bankruptcy distributions, and other official forced distributions",
      entry: "Blocked until official event, parent-holder, inactive-listing, adjusted-price, and point-in-time quality histories are complete",
      ranking: "No proxy signal is permitted; news keywords and current listings cannot substitute for the missing event history",
      sizing: "The registered hypothesis remains flat until its data contract passes",
    };
  }

  if (strategyKey === "us_factor_sleeve_v1") {
    return {
      universe: `${universe}, selected by liquidity observable before the test window`,
      entry: "All four point-in-time factors required: book-to-price, TTM quality, 12-1 momentum, and low issuance",
      ranking: "Cross-sectional percentile composite with a monthly turnover buffer; SEC amendments affect only later rebalances",
      sizing: "30-50 names, 3% signal cap, bounded inverse-volatility tilt, next-close fills, and realistic plus 10/30/50 bps costs",
    };
  }

  return {
    universe: `${universe} defined by the registered experiment`,
    entry: "Only securities passing the registered point-in-time entry gates are eligible",
    ranking: "Passing securities use the strategy's versioned ranking; queue urgency is not used",
    sizing: "The registered deterministic risk policy controls target size and portfolio exposure",
  };
}
