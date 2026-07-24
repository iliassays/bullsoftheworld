import type {
  DecisionEvent,
  InvestmentOperatingView,
  ShadowPortfolio,
  ShadowSnapshot,
} from "../../app/api-client";
import type { AutonomousDecision } from "../autonomous-research/model";

export type DecisionTicketAction =
  | "no_action"
  | "investigate"
  | "monitor"
  | "target"
  | "held"
  | "reduce"
  | "exit"
  | "blocked";

export interface DecisionTicket {
  action: DecisionTicketAction;
  label: string;
  tone: "neutral" | "positive" | "warning" | "negative";
  source: "portfolio_ledger" | "research_record" | "none";
  portfolioName: string | null;
  strategyKey: string | null;
  effectiveDate: string | null;
  targetWeightPct: number | null;
  currentWeightPct: number | null;
  shares: number | null;
  averageCost: number | null;
  latestFillPrice: number | null;
  rationale: string;
  execution: string;
  invalidation: string;
  risk: string;
  nextReview: string;
  event: DecisionEvent | null;
}

interface TicketInput {
  ticker: string;
  currentPrice: number;
  evidenceFreshness: "fresh" | "aging" | "gap";
  candidateInvalidation: string;
  capacity: string;
  exitDays: number;
  decision: AutonomousDecision | null;
  portfolios: readonly ShadowPortfolio[];
  operatingView: InvestmentOperatingView | undefined;
}

interface PortfolioContext {
  portfolio: ShadowPortfolio;
  snapshot: ShadowSnapshot;
  events: DecisionEvent[];
  latestEvent: DecisionEvent | null;
  position: { shares: number; average_cost: number } | undefined;
  targetWeight: number;
  currentWeightPct: number | null;
}

function latestSnapshot(portfolio: ShadowPortfolio): ShadowSnapshot | undefined {
  return [...portfolio.snapshots].sort(
    (left, right) =>
      right.asOfDate.localeCompare(left.asOfDate) || right.sessionNumber - left.sessionNumber,
  )[0];
}

function latestEvent(events: readonly DecisionEvent[]): DecisionEvent | null {
  return [...events].sort(
    (left, right) =>
      right.effectiveDate.localeCompare(left.effectiveDate) || right.sequence - left.sequence,
  )[0] ?? null;
}

function numeric(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function eventFillPrice(event: DecisionEvent | null): number | null {
  return event?.eventType === "fill" ? numeric(event.payload.fill_price) : null;
}

function contextPriority(context: PortfolioContext): number {
  if (context.position) return 4;
  if (context.targetWeight > 0) return 3;
  if (context.latestEvent) return 2;
  return 1;
}

function portfolioContext(
  input: TicketInput,
  portfolio: ShadowPortfolio,
): PortfolioContext | null {
  const snapshot = latestSnapshot(portfolio);
  if (!snapshot) return null;
  const operating = input.operatingView?.portfolios.find(
    (item) => item.portfolioId === portfolio.id,
  );
  const events = (operating?.recentEvents ?? []).filter(
    (event) => event.code?.toUpperCase() === input.ticker,
  );
  const position = snapshot.positions[input.ticker];
  const targetWeight = snapshot.targetWeights[input.ticker] ?? 0;
  if (!position && targetWeight <= 0 && events.length === 0) return null;
  const currentWeightPct =
    position && snapshot.nav > 0
      ? (position.shares * input.currentPrice * 100) / snapshot.nav
      : null;
  return {
    portfolio,
    snapshot,
    events,
    latestEvent: latestEvent(events),
    position,
    targetWeight,
    currentWeightPct,
  };
}

function selectContext(input: TicketInput): PortfolioContext | null {
  return input.portfolios
    .filter((portfolio) => portfolio.status === "active")
    .flatMap((portfolio) => {
      const context = portfolioContext(input, portfolio);
      return context ? [context] : [];
    })
    .sort(
      (left, right) =>
        contextPriority(right) - contextPriority(left) ||
        (right.latestEvent?.effectiveDate ?? right.snapshot.asOfDate).localeCompare(
          left.latestEvent?.effectiveDate ?? left.snapshot.asOfDate,
        ),
    )[0] ?? null;
}

function latestFill(events: readonly DecisionEvent[]): DecisionEvent | null {
  return latestEvent(events.filter((event) => event.eventType === "fill"));
}

function portfolioTicket(input: TicketInput, context: PortfolioContext): DecisionTicket {
  const targetWeightPct = context.targetWeight * 100;
  const currentWeightPct = context.currentWeightPct;
  const event = context.latestEvent;
  const fill = latestFill(context.events);
  const breachedLimits =
    input.operatingView?.portfolios.find(
      (item) => item.portfolioId === context.portfolio.id,
    )?.risk.breachedLimits ?? [];

  let action: DecisionTicketAction;
  if (context.position && targetWeightPct <= 0) {
    action = "exit";
  } else if (
    context.position &&
    currentWeightPct !== null &&
    targetWeightPct < currentWeightPct - 0.25
  ) {
    action = "reduce";
  } else if (context.position) {
    action = "held";
  } else if (targetWeightPct > 0) {
    action = "target";
  } else {
    action = event?.eventType === "rejection" || event?.eventType === "risk"
      ? "blocked"
      : "no_action";
  }

  const labels: Record<DecisionTicketAction, string> = {
    no_action: "No registered portfolio action",
    investigate: "Research investigation",
    monitor: "Monitor for evidence change",
    target: "Target registered for next session",
    held: "Held in shadow book",
    reduce: "Reduction target registered",
    exit: "Exit target registered",
    blocked: "Portfolio action blocked",
  };
  const tones: Record<DecisionTicketAction, DecisionTicket["tone"]> = {
    no_action: "neutral",
    investigate: "neutral",
    monitor: "warning",
    target: "positive",
    held: "positive",
    reduce: "warning",
    exit: "negative",
    blocked: "negative",
  };
  const latestFillPrice = eventFillPrice(fill);
  const eventDate = event?.effectiveDate ?? context.snapshot.asOfDate;
  const positionText = context.position
    ? `${context.position.shares.toLocaleString("en-US")} shadow shares at ${context.position.average_cost.toFixed(2)} average cost.`
    : `The active book registered a ${targetWeightPct.toFixed(1)}% target.`;

  return {
    action,
    label: labels[action],
    tone: tones[action],
    source: "portfolio_ledger",
    portfolioName: context.portfolio.name,
    strategyKey: context.portfolio.strategyKey,
    effectiveDate: eventDate,
    targetWeightPct,
    currentWeightPct,
    shares: context.position?.shares ?? null,
    averageCost: context.position?.average_cost ?? null,
    latestFillPrice,
    rationale: positionText,
    execution:
      action === "target" || action === "reduce" || action === "exit"
        ? `Earliest modeled execution is the next observable session open after ${eventDate}, with strategy costs.`
        : latestFillPrice !== null
          ? `Latest modeled fill was ${latestFillPrice.toFixed(2)} on ${fill?.effectiveDate}.`
          : "No unexecuted order is registered for this security.",
    invalidation:
      input.decision?.invalidationRules[0] ??
      input.candidateInvalidation ??
      "No explicit thesis invalidation is registered.",
    risk:
      breachedLimits.length > 0
        ? `Portfolio limits breached: ${breachedLimits.join(", ")}.`
        : `${input.capacity} implementation capacity; modeled exit policy ${input.exitDays.toFixed(1)} sessions.`,
    nextReview:
      input.evidenceFreshness === "fresh"
        ? "Re-evaluate after the next completed session or material official evidence."
        : input.evidenceFreshness === "gap"
          ? "Evidence has a coverage gap; refresh the fact ledger before increasing exposure."
          : "Evidence is aging; refresh the fact ledger before increasing exposure.",
    event,
  };
}

function researchTicket(input: TicketInput): DecisionTicket {
  const decision = input.decision;
  const action: DecisionTicketAction =
    decision?.status === "qualified"
      ? "investigate"
      : decision?.status === "monitor"
        ? "monitor"
        : decision?.status === "rejected" || decision?.status === "abstained"
          ? "blocked"
          : "no_action";
  const label: Record<DecisionTicketAction, string> = {
    no_action: "No registered portfolio action",
    investigate: "Research qualified; no target registered",
    monitor: "Monitor; no target registered",
    target: "Target registered for next session",
    held: "Held in shadow book",
    reduce: "Reduction target registered",
    exit: "Exit target registered",
    blocked: decision ? "Research gate did not qualify" : "Portfolio action blocked",
  };
  return {
    action,
    label: label[action],
    tone: action === "monitor" ? "warning" : action === "blocked" ? "negative" : "neutral",
    source: decision ? "research_record" : "none",
    portfolioName: null,
    strategyKey: decision?.strategyKey ?? null,
    effectiveDate: null,
    targetWeightPct: null,
    currentWeightPct: null,
    shares: null,
    averageCost: null,
    latestFillPrice: null,
    rationale:
      decision?.headline ??
      "No autonomous research decision or append-only portfolio target exists at this cutoff.",
    execution:
      "No order is implied. A registered strategy target and portfolio-risk approval are required.",
    invalidation:
      decision?.invalidationRules[0] ??
      input.candidateInvalidation ??
      "No explicit thesis invalidation is registered.",
    risk: `${input.capacity} implementation capacity; modeled exit policy ${input.exitDays.toFixed(1)} sessions.`,
    nextReview:
      decision?.nextEvidence[0]?.question ??
      "Re-evaluate after a completed-session or official-evidence change.",
    event: null,
  };
}

export function buildDecisionTicket(input: TicketInput): DecisionTicket {
  const normalizedInput = { ...input, ticker: input.ticker.trim().toUpperCase() };
  const context = selectContext(normalizedInput);
  return context ? portfolioTicket(normalizedInput, context) : researchTicket(normalizedInput);
}
