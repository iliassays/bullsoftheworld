import type {
  DecisionCandidate,
  DecisionCandidateState,
} from "../../app/api-client";

export type DecisionBoardFilter = "all" | "entries" | "positions" | "exits";

export function decisionStateLabel(state: DecisionCandidateState): string {
  if (state === "ready") return "Entry target";
  if (state === "manage") return "Active position";
  if (state === "exit") return "Exit target";
  if (state === "blocked") return "Blocked";
  return "Closed";
}

export function matchesDecisionFilter(
  candidate: DecisionCandidate,
  filter: DecisionBoardFilter,
): boolean {
  if (filter === "entries") return candidate.state === "ready" || candidate.state === "blocked";
  if (filter === "positions") return candidate.state === "manage";
  if (filter === "exits") return candidate.state === "exit" || candidate.state === "closed";
  return true;
}

export function matchesCapTier(candidate: DecisionCandidate, capTier: string): boolean {
  return capTier === "all" || candidate.capTier === capTier;
}
