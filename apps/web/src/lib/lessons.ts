// Short, example-driven lessons: not "what is X" (the tooltip covers that) but "how do traders
// actually USE X to decide" — with a worked, real-ticker example. Descriptive education, never advice.
export interface Lesson {
  title: string;
  what: string;
  use: string;
  watch: string;
  example: string;
}

export const LESSONS: Record<string, Lesson> = {
  momentum: {
    title: "Momentum (12-month trend)",
    what: "How strongly a stock has trended over the past year, skipping the last month (which tends to reverse).",
    use: "Momentum traders ride stocks that keep climbing. They pair it with the long-term trend (above the 200-day average) and look to enter on small dips rather than chase a spike.",
    watch: "Momentum can reverse hard — especially in a market like DSE. A huge recent jump plus a high RSI means 'stretched', not 'strong'.",
    example: "SQURPHARMA up ~40% over the year and still above its 200-day average looks like an intact uptrend. A 600% penny-stock spike is far more likely a pump than a trend.",
  },
  value_pe: {
    title: "Value (cheap vs sector)",
    what: "Price-to-earnings (P/E) compared with the stock's own sector. Below the sector median = cheaper than peers.",
    use: "Value investors buy sound companies trading below their peers, betting the gap closes. They confirm earnings are real and steady, not collapsing.",
    watch: "'Cheap' can mean the market sees trouble — a value trap. Always check WHY it's cheap, and pair it with quality (ROE) and the news.",
    example: "A profitable bank at P/E 8 while its sector sits at 12 looks genuinely cheap. A loss-making firm at a low P/E is cheap for a reason.",
  },
  roe: {
    title: "Quality (return on equity)",
    what: "ROE = profit ÷ shareholder capital — how much profit the company earns on each taka of net worth.",
    use: "Quality investors favour consistently high ROE (15%+): a sign of a strong, efficient business. It pairs well with value to avoid traps.",
    watch: "One great year isn't quality — look for consistency. Sky-high ROE built on heavy debt is riskier than it looks.",
    example: "GP and RECKITT earn 40%+ ROE — classic quality names. A 3% ROE business is barely beating a bank deposit.",
  },
  dividend: {
    title: "Dividend yield",
    what: "Last year's cash dividend as a percentage of today's price.",
    use: "Income investors hold steady payers for regular cash, checking the company can keep paying (profits, manageable debt).",
    watch: "A very high yield usually means the price crashed (a trap), not generosity. Bonus (stock) dividends aren't cash.",
    example: "A stable company paying 6% on a steady price is real income. A '25% yield' on a ৳3 collapsed stock is a warning sign.",
  },
  volatility: {
    title: "Volatility (steadiness)",
    what: "How big the day-to-day price swings are over the past year.",
    use: "Conservative investors prefer low-volatility names for a calmer ride that's easier to hold through ups and downs — often blue chips.",
    watch: "Low volatility means smoother, not higher returns. Extremely low can also signal thin trading.",
    example: "RECKITT and MARICO swing ~12% a year (steady); a hot small-cap can swing 60%+.",
  },
  rsi: {
    title: "RSI (overbought / oversold)",
    what: "A 0–100 momentum gauge: above 70 = overbought (run up fast), below 30 = oversold (fallen fast).",
    use: "Mean-reversion traders watch the extremes as a heads-up — not a trigger. In a strong trend, overbought can stay overbought for a while.",
    watch: "RSI alone isn't a signal. Oversold works better on beaten-down, thinly-traded names; overbought matters most right after a big run.",
    example: "RSI 75 on a stock that just spiked = stretched; many traders wait for it to cool before entering.",
  },
  moneyflow: {
    title: "Money flow (CMF)",
    what: "Whether recent volume is pushing the price up (buyers in control) or down (sellers in control).",
    use: "It confirms a move: a rising price with money flowing in is more convincing than a rise on no real buying.",
    watch: "It's a short-term read and flips quickly — use it to confirm, not to predict.",
    example: "A breakout with strong inflow is more believable than one on thin volume.",
  },
  volume: {
    title: "Volume & turnover",
    what: "How much is trading versus normal (unusual volume), or in total money terms (most active).",
    use: "A volume spike means something is happening — news, a breakout, or a pump. Traders find out WHY before acting.",
    watch: "Big volume on a penny stock can be a pump. Look at turnover (money), not just share count, and find the reason.",
    example: "4× the usual volume on a results day is real interest; 4× on no news is suspicious.",
  },
  smartmoney: {
    title: "Institutions & foreign buying",
    what: "Whether institutions and foreign investors raised their stake at the last monthly disclosure.",
    use: "Retail often treats 'smart money' accumulation as a vote of confidence in a name.",
    watch: "Disclosures are monthly and backward-looking — it's history, not a live signal, and big players can be wrong too.",
    example: "Institutions adding 5 pp over a month suggests growing conviction — but the data is already a few weeks old.",
  },
};

// Which lesson backs each screen (by screen key). Screens without an entry just show the tooltip.
export const SCREEN_LESSON: Record<string, string> = {
  momentum_12_1: "momentum",
  top_gainers: "momentum",
  top_losers: "momentum",
  value_vs_sector: "value_pe",
  quality_roe: "roe",
  dividend_yield: "dividend",
  low_volatility: "volatility",
  oversold: "rsi",
  overbought: "rsi",
  accumulation: "moneyflow",
  distribution: "moneyflow",
  unusual_volume: "volume",
  most_active: "volume",
  smart_money_buying: "smartmoney",
};
