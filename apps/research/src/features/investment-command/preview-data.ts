import { researchDeployment } from "../../app/deployment";
import type {
  DecisionBoard,
  DecisionCandidate,
  DecisionCandidatePath,
  DecisionCandidateState,
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
