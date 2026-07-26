import { researchDeployment } from "../../app/deployment";
import type {
  DecisionBoard,
  DecisionCandidate,
  DecisionCandidatePath,
  DecisionCandidateState,
  SqueezeMonitor,
  SqueezePath,
  StrategyReadinessBoard,
} from "../../app/api-client";

const market = researchDeployment.market;
const tenantId = researchDeployment.tenant;
const workspaceId = "00000000-0000-0000-0000-000000000301";
const dates = ["2026-07-23", "2026-07-22", "2026-07-21", "2026-07-20"];

const identities = market === "DSE"
  ? [
      ["BRACBANK", "BRAC Bank PLC", "ready", 3.6],
      ["BXPHARMA", "Beximco Pharmaceuticals", "manage", 7.8],
      ["ENVOYTEX", "Envoy Textiles", "exit", -2.4],
    ] as const
  : [
      ["NXTC", "NextCure, Inc.", "ready", 5.9],
      ["AGEN", "Agenus Inc.", "manage", 11.7],
      ["QTTB", "Q32 Bio Inc.", "blocked", -3.1],
    ] as const;

function candidate(
  code: string,
  company: string,
  state: DecisionCandidateState,
  returnPct: number,
  index: number,
): DecisionCandidate {
  const discoveryPrice = market === "DSE" ? 48 + index * 17 : 3.2 + index * 1.8;
  return {
    id: `00000000-0000-0000-0000-00000000040${index}:${code}`,
    portfolioId: `00000000-0000-0000-0000-00000000040${index}`,
    portfolioName: `${market} systematic shadow`,
    strategyKey: market === "DSE" ? "dse_reversal_v1" : "us_breakout_v1",
    strategyName: market === "DSE" ? "DSE liquid reversal" : "US liquid trend participation",
    direction: "long",
    horizon: "swing",
    expectedHolding: market === "DSE"
      ? "Approximately 5-20 completed sessions"
      : "Approximately 10-40 completed sessions",
    code,
    company,
    capTier: index === 0 ? "small" : index === 1 ? "mid" : "micro",
    state,
    evidenceMode: index === 2 ? "historical_replay" : "forward",
    asOfDate: dates[0]!,
    firstDiscoveredOn: dates[Math.min(index + 1, dates.length - 1)]!,
    isNew: index === 0,
    discoveryPrice,
    asOfPrice: discoveryPrice * (1 + returnPct / 100),
    returnSinceDiscoveryPct: returnPct,
    maxFavorablePct: returnPct + 3.2,
    maxAdversePct: Math.min(-1.6, returnPct - 4.4),
    sessionsSinceDiscovery: 4 + index * 6,
    targetWeightPct: state === "exit" ? 0 : 8 - index,
    positionWeightPct: state === "manage" || state === "exit" ? 7.1 : 0,
    latestFillSide: state === "manage" || state === "exit" ? "buy" : null,
    latestFillPrice: state === "manage" || state === "exit" ? discoveryPrice * 1.01 : null,
    latestFillDate: state === "manage" || state === "exit" ? dates[2]! : null,
    riskReferencePrice: state === "ready" || state === "manage" ? discoveryPrice : null,
    invalidationPrice: state === "ready" || state === "manage" ? discoveryPrice * 0.9 : null,
    planningObjectivePrice: state === "ready" || state === "manage" ? discoveryPrice * 1.2 : null,
    planningRewardRisk: state === "ready" || state === "manage" ? 2 : null,
    exitPolicy: "A 10% position stop, target removal or portfolio-level risk control can close the paper position.",
    headline: state === "ready"
      ? "Entry target is waiting for execution"
      : state === "manage"
        ? "Paper position remains active"
        : state === "exit"
          ? "Exit target is waiting for execution"
          : "The desired action was blocked",
    story: `${company} is shown because the registered ${market} strategy changed its target. The archived state remains separate from any completed fill.`,
    riskNotes: state === "blocked" ? ["Liquidity participation prevented the intended order."] : [],
  };
}

export const previewDecisionBoard: DecisionBoard = {
  workspaceId,
  tenantId,
  market,
  generatedAt: "2026-07-23T18:00:00Z",
  selectedDate: dates[0]!,
  latestDate: dates[0]!,
  availableDates: dates,
  directionCapabilities: [
    {
      direction: "long",
      status: "active",
      reason: "Registered long strategies have complete execution and portfolio-risk controls.",
    },
    {
      direction: "short",
      status: "blocked",
      reason: "Point-in-time borrow availability, locate outcomes and borrow fees are not available.",
    },
  ],
  candidates: identities.map(([code, company, state, returnPct], index) =>
    candidate(code, company, state, returnPct, index)
  ),
  methodology: "Preview of the immutable decision archive and adjusted discovery-price follow-through.",
};

export function previewDecisionPath(
  portfolioId: string,
  code: string,
): DecisionCandidatePath {
  const selected = previewDecisionBoard.candidates.find(
    (item) => item.portfolioId === portfolioId && item.code === code,
  ) ?? previewDecisionBoard.candidates[0]!;
  const start = selected.discoveryPrice ?? 10;
  const totalDiscoveryDays = Math.max(
    Math.round(
      (Date.parse(`${selected.asOfDate}T00:00:00Z`) -
        Date.parse(`${selected.firstDiscoveredOn}T00:00:00Z`)) /
        86_400_000,
    ),
    1,
  );
  const points = Array.from({ length: 84 }, (_, index) => {
    const date = new Date(Date.UTC(2026, 4, 1 + index));
    const dateString = date.toISOString().slice(0, 10);
    const discoveryOffset = Math.round(
      (Date.parse(`${dateString}T00:00:00Z`) -
        Date.parse(`${selected.firstDiscoveredOn}T00:00:00Z`)) /
        86_400_000,
    );
    const progress = Math.min(Math.max(discoveryOffset / totalDiscoveryDays, 0), 1);
    const close = discoveryOffset >= 0
      ? start * (
        1 +
        (selected.returnSinceDiscoveryPct ?? 0) / 100 * progress +
        Math.sin(progress * Math.PI) * 0.018
      )
      : start * (1 + Math.sin(discoveryOffset / 4) * 0.018 + discoveryOffset * 0.001);
    return {
      date: dateString,
      close,
      volume: 180_000 + ((index * 73_211) % 640_000),
      returnSinceDiscoveryPct: discoveryOffset >= 0 ? (close / start - 1) * 100 : null,
    };
  });
  return {
    workspaceId,
    tenantId,
    market,
    candidate: selected,
    points,
    events: [],
    priceBasis: "Adjusted completed-session close.",
  };
}

export const previewStrategyReadiness: StrategyReadinessBoard = {
  market,
  tenantId,
  generatedAt: "2026-07-24T12:00:00Z",
  methodology:
    "Statuses come from the 2026-07-24 data audit: backtest_ready requires point-in-time "
    + "inputs for a gated historical run; diagnostic_only means a known data defect caps every "
    + "result below promotion; blocked means a required dataset does not exist.",
  entries: market === "DSE"
    ? [
        {
          key: "dse_reversal_v1",
          name: "DSE liquid mean reversion",
          market,
          direction: "long",
          horizon: "swing",
          implementedStrategyKey: "dse_reversal_v1",
          status: "diagnostic_only",
          economicHypothesis:
            "Retail-dominated overreaction in liquid DSE names mean-reverts over days to weeks.",
          rationale:
            "Runs on raw closes with bonus/rights issues unadjusted, on ~2 years of history.",
          missingData: [
            {
              key: "dse_corporate_action_adjustments",
              description: "DSE daily bars carry no adjusted closes.",
            },
            {
              key: "dse_price_history_depth",
              description: "DSE bars start 2024-06-27 (~492 sessions).",
            },
          ],
        },
        {
          key: "dse_scalp",
          name: "DSE intraday scalping",
          market,
          direction: "long",
          horizon: "scalp",
          implementedStrategyKey: null,
          status: "blocked",
          economicHypothesis: "Intraday liquidity provision / momentum bursts.",
          rationale: "Four sessions of intraday data; no execution evidence of any kind.",
          missingData: [
            {
              key: "dse_intraday_history",
              description: "DSE intraday capture began 2026-07-20 (four sessions).",
            },
          ],
        },
      ]
    : [
        {
          key: "us_breakout_v1",
          name: "US volatility-contraction breakout",
          market,
          direction: "long",
          horizon: "swing",
          implementedStrategyKey: "us_breakout_v1",
          status: "diagnostic_only",
          economicHypothesis:
            "Range compression with rising participation resolves upward when supply is absorbed.",
          rationale:
            "The stored universe is survivors-only and historical membership is unreconstructable.",
          missingData: [
            {
              key: "us_delisted_price_history",
              description: "Delisted/acquired US price histories are missing.",
            },
          ],
        },
        {
          key: "us_short_breakdown",
          name: "US short-side breakdown / failed breakout",
          market,
          direction: "short",
          horizon: "swing",
          implementedStrategyKey: null,
          status: "blocked",
          economicHypothesis: "Distribution and failed breakouts resolve downward.",
          rationale:
            "No paper short may ever fill without borrow/locate/fee/recall data.",
          missingData: [
            {
              key: "us_borrow_locate_dataset",
              description:
                "Point-in-time borrow availability, locate outcomes, borrow fees and squeeze controls.",
            },
          ],
        },
      ],
};

const squeezeEntry = (code: string, company: string, state: "trigger_ready" | "confirmed") => ({
  market,
  code,
  company,
  capTier: "small",
  evidenceMode: "forward" as const,
  family: market === "DSE" ? "supply_constrained_breakout" : "compression_breakout",
  familyLabel: market === "DSE" ? "Supply-constrained breakout" : "Compression breakout setup",
  state,
  previousState: state === "confirmed" ? "trigger_ready" : "forming",
  stateReason:
    state === "confirmed"
      ? "Close exceeded the 20-session base high within the last 3 sessions with relative volume ≥ 1.5x."
      : "Base is tight (5-session range within 1.5 ATR) and price sits within 3% of the base high.",
  isNew: state !== "confirmed",
  isNewConfirmation: state === "confirmed",
  firstDiscoveredOn: "2026-07-21",
  asOfDate: "2026-07-23",
  sessionsSinceDiscovery: 3,
  discoveryPrice: market === "DSE" ? 54 : 12.4,
  asOfPrice: market === "DSE" ? 56.7 : 13.1,
  returnSinceDiscoveryPct: 5.0,
  firstConfirmedOn: state === "confirmed" ? "2026-07-23" : null,
  confirmationPrice: state === "confirmed" ? 56.7 : null,
  moveToConfirmationPct: state === "confirmed" ? 5.0 : null,
  nextObservableOn: null,
  nextObservablePrice: null,
  returnSinceNextObservablePct: null,
  maxFavorablePct: 6.2,
  maxAdversePct: -1.1,
  // Traded extremes always bracket the close-based pair.
  peakTradedPct: 8.9,
  troughTradedPct: -3.4,
  setupPrice: market === "DSE" ? 56.7 : 13.1,
  triggerPrice: market === "DSE" ? 57.4 : 13.4,
  invalidationPrice: market === "DSE" ? 53.2 : 11.9,
  riskPerShare: market === "DSE" ? 4.2 : 1.5,
  planningObjectivePrice: market === "DSE" ? 65.8 : 16.4,
  planningRewardRisk: 2.0,
  expectedHolding: "Approximately 10-40 completed sessions",
  liquidityCapacityNote: "About 0.42M per session at 2% of 20-session average traded value.",
  supportingEvidence: [
    "Volatility contraction: 14-session ATR fell ≥20% over 20 sessions.",
    ...(market === "DSE"
      ? ["Free float is only 24% of market capitalization (supply scarcity)."]
      : ["Short-marked volume share elevated (66% 5-session, volume-weighted) — this is not short interest and cannot establish positioning."]),
  ],
  counterEvidence: market === "US" ? ["Recent financing/dilution filing (S-1/S-3/424B family) within 90 days."] : [],
  dataQuality:
    market === "DSE"
      ? ["DSE prices are raw exchange closes without corporate-action adjustment; a bonus or rights ex-date can flip this state."]
      : ["US universe currently stores survivors only; archived setups over-represent companies that did not delist."],
  missingEvidence: [],
  paperBookStatus:
    market === "DSE"
      ? "Locked forward collection only; this remains outside paper capital."
      : "No paper book — this family has not passed its promotion gates.",
  methodologyVersion: "squeeze-monitor-v3",
});

export const previewSqueezeMonitor: SqueezeMonitor = {
  market,
  tenantId,
  generatedAt: "2026-07-24T13:40:00Z",
  selectedDate: "2026-07-23",
  latestDate: "2026-07-23",
  availableDates: ["2026-07-23", "2026-07-22", "2026-07-21"],
  methodologyVersion: "squeeze-monitor-v3",
  methodology:
    "The current engine is squeeze-monitor-v3. States are written once per completed "
    + "session after the analytics refresh; historical rows retain their own method.",
  limitations: [
    "FINRA daily short-marked volume is not short interest, cannot establish open short positions or days-to-cover, and appears only as labeled supporting context.",
    "States are a diagnostic taxonomy (squeeze-monitor-v3); no family has passed the registered validation and promotion gates.",
  ],
  families: [
    ...(market === "DSE"
      ? [
          {
            family: "supply_constrained_breakout",
            label: "Supply-constrained breakout",
            status: "available" as const,
            blockedReason: null,
            missingDatasets: [],
            entries: [squeezeEntry("BXPHARMA", "Beximco Pharmaceuticals", "confirmed")],
          },
        ]
      : []),
    {
      family: "compression_breakout",
      label: "Compression breakout setup",
      status: "available" as const,
      blockedReason: null,
      missingDatasets: [],
      entries:
        market === "US"
          ? [squeezeEntry("NXTC", "NextCure, Inc.", "trigger_ready")]
          : [squeezeEntry("BRACBANK", "BRAC Bank PLC", "trigger_ready")],
    },
    {
      family: "failed_breakdown_reversal",
      label: "Failed-breakdown reversal",
      status: "available" as const,
      blockedReason: null,
      missingDatasets: [],
      entries: [],
    },
    ...(market === "US"
      ? [
          {
            family: "us_short_squeeze",
            label: "US short squeeze",
            status: "data_blocked" as const,
            blockedReason:
              "No authoritative short-positioning data exists in Atlas. FINRA daily short-marked volume cannot establish open positions or days-to-cover.",
            missingDatasets: [
              "Point-in-time short interest as % of float and days-to-cover (FINRA bi-monthly settlement data).",
              "Borrow availability, utilization, cost-to-borrow, locate outcomes.",
              "SEC failures-to-deliver files and Reg SHO threshold status.",
            ],
            entries: [],
          },
          {
            family: "us_gamma_squeeze",
            label: "US gamma/options squeeze",
            status: "data_blocked" as const,
            blockedReason:
              "No option-chain history exists; option volume without opening/closing classification cannot prove new positioning.",
            missingDatasets: ["Options OI, volume, IV, Greeks with chain history."],
            entries: [],
          },
        ]
      : []),
  ],
};

/** Deterministic synthetic candles so the preview chart exercises every overlay and level. */
export function previewSqueezePath(family: string, code: string): SqueezePath {
  const anchorPrice = market === "DSE" ? 54 : 12.4;
  // 120 calendar sessions ending on the preview archive date (2026-07-23).
  const start = new Date("2026-03-26T00:00:00Z");
  const closes: number[] = [];
  for (let index = 0; index < 120; index += 1) {
    // A drifting base that tightens, then breaks out over the final sessions.
    const drift = anchorPrice * (0.9 + index * 0.0012);
    const wobble = Math.sin(index / 6) * anchorPrice * (index > 90 ? 0.004 : 0.02);
    const thrust = index > 110 ? anchorPrice * 0.008 * (index - 110) : 0;
    closes.push(Number((drift + wobble + thrust).toFixed(2)));
  }
  const ema = (period: number) => {
    const out: (number | null)[] = closes.map(() => null);
    if (closes.length < period) return out;
    const multiplier = 2 / (period + 1);
    let value = closes.slice(0, period).reduce((sum, item) => sum + item, 0) / period;
    out[period - 1] = value;
    for (let index = period; index < closes.length; index += 1) {
      value = (closes[index]! - value) * multiplier + value;
      out[index] = Number(value.toFixed(4));
    }
    return out;
  };
  const ema20 = ema(20);
  const ema50 = ema(50);
  const anchorIndex = closes.length - 3;
  let cumulativeValue = 0;
  let cumulativeVolume = 0;
  const points = closes.map((close, index) => {
    const date = new Date(start.getTime() + index * 86_400_000).toISOString().slice(0, 10);
    const spread = close * (index > 90 ? 0.006 : 0.018);
    const open = Number((close - spread * 0.3).toFixed(2));
    const high = Number((close + spread).toFixed(2));
    const low = Number((close - spread).toFixed(2));
    const volume = Math.round(400_000 * (index > 110 ? 2.2 : index > 90 ? 0.7 : 1));
    let anchoredVwap: number | null = null;
    if (index >= anchorIndex) {
      cumulativeValue += ((high + low + close) / 3) * volume;
      cumulativeVolume += volume;
      anchoredVwap = Number((cumulativeValue / cumulativeVolume).toFixed(4));
    }
    return { date, open, high, low, close, volume, ema20: ema20[index] ?? null, ema50: ema50[index] ?? null, anchoredVwap };
  });
  return {
    market,
    tenantId,
    family,
    familyLabel: market === "DSE" ? "Supply-constrained breakout" : "Compression breakout setup",
    entry: squeezeEntry(code, market === "DSE" ? "Beximco Pharmaceuticals" : "Preview Industries", "confirmed"),
    points,
    stateHistory: [
      {
        date: points[Math.max(0, points.length - 40)]!.date,
        state: "forming",
        previousState: "none",
        reason: "An earlier compressed base was discovered.",
        episodeNumber: 1,
        isCurrentEpisode: false,
      },
      {
        date: points[Math.max(0, points.length - 36)]!.date,
        state: "confirmed",
        previousState: "forming",
        reason: "The earlier breakout confirmed.",
        episodeNumber: 1,
        isCurrentEpisode: false,
      },
      {
        date: points[points.length - 3]!.date,
        state: "watch",
        previousState: "none",
        reason: "Within 15% of the 52-week high.",
        episodeNumber: 2,
        isCurrentEpisode: true,
      },
      {
        date: points[points.length - 2]!.date,
        state: "trigger_ready",
        previousState: "watch",
        reason: "Base is tight and price sits within 3% of the base high.",
        episodeNumber: 2,
        isCurrentEpisode: true,
      },
      {
        date: points[points.length - 1]!.date,
        state: "confirmed",
        previousState: "trigger_ready",
        reason: "Close exceeded the 20-session base high with relative volume ≥ 1.5x.",
        episodeNumber: 2,
        isCurrentEpisode: true,
      },
    ],
    discoveryNumber: 2,
    priorDiscoveryDates: [points[Math.max(0, points.length - 40)]!.date],
    atr14: market === "DSE" ? 1.12 : 0.26,
    atr14Prior: market === "DSE" ? 1.68 : 0.39,
    atrChangePct: -33.3,
    priceBasis:
      market === "US"
        ? "Split/distribution-adjusted completed sessions."
        : "Raw completed DSE exchange closes — no corporate-action adjustment exists, so a bonus or rights ex-date appears as a price drop.",
    overlayBasis:
      "EMA 20/50 from completed closes. Anchored VWAP is computed from daily typical price x volume anchored at first discovery — Atlas has no intraday history, so this is not an intraday session VWAP.",
  };
}
