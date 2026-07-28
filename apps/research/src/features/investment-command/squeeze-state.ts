import type { SqueezeEntry, SqueezeState } from "../../app/api-client";
import type { StatusTone } from "../../design-system";

export const SQUEEZE_STATE_LABEL: Record<SqueezeState, string> = {
  watch: "Watch",
  forming: "Forming",
  trigger_ready: "Trigger ready",
  confirmed: "Confirmed",
  exhausted: "Too extended",
  failed: "Failed",
};

export const SQUEEZE_STATE_TONE: Record<SqueezeState, StatusTone> = {
  watch: "neutral",
  forming: "warning",
  trigger_ready: "warning",
  confirmed: "positive",
  exhausted: "negative",
  failed: "negative",
};

export function squeezeStateLabel(state: string): string {
  return SQUEEZE_STATE_LABEL[state as SqueezeState] ?? state.replace(/_/g, " ");
}

export function squeezeReferenceCopy(entry: SqueezeEntry): {
  label: string;
  detail: string;
} {
  if (entry.family === "failed_breakdown_reversal") {
    return { label: "Reclaim level", detail: "rule reference" };
  }
  return { label: "Base high", detail: "crossing alone does not confirm" };
}
