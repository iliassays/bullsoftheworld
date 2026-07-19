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

  if (strategyKey === "dse_quality_value_v1") {
    return {
      universe: `${universe}, ranked by completed-session traded value`,
      entry: "Two annual observations known by the signal close; positive and improving EPS, positive NAV and profit, ROE proxy at least 8%, P/E at most 18, P/B at most 2.5, no severe 63-session deterioration, and at least BDT 2m average daily value",
      ranking: "Passing companies rank by earnings improvement, profitability, earnings and book yield, participation, momentum, and volatility; later revisions are invisible",
      sizing: "20-session rebalance, rank buffer, target volatility, 12% position cap, 30% sector cap, 85% gross cap, liquidity, fees, slippage, and DSE settlement",
    };
  }

  return {
    universe: `${universe} defined by the registered experiment`,
    entry: "Only securities passing the registered point-in-time entry gates are eligible",
    ranking: "Passing securities use the strategy's versioned ranking; queue urgency is not used",
    sizing: "The registered deterministic risk policy controls target size and portfolio exposure",
  };
}
