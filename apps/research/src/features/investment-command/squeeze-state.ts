import type { SqueezeEntry, SqueezeState } from "../../app/api-client";
import type { StatusTone } from "../../design-system";

export const SQUEEZE_STATE_LABEL: Record<SqueezeState, string> = {
  watch: "Early watch",
  forming: "Base forming",
  trigger_ready: "Near trigger",
  confirmed: "Rule confirmed",
  exhausted: "Too extended",
  failed: "Invalidated",
};

export const SQUEEZE_STATE_EXPLANATION: Record<SqueezeState, string> = {
  watch: "Early evidence exists, but the setup structure is not developed yet.",
  forming: "The base is developing; the trigger conditions are not ready.",
  trigger_ready:
    "Price is near the rule level; confirmation still needs a completed close and the required participation.",
  confirmed:
    "The completed-session setup rule was met. This is research evidence, not an order or a probability claim.",
  exhausted: "Price is too extended from its reference trend for a fresh setup.",
  failed: "The archived setup invalidated and is no longer active.",
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
