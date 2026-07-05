import type { PatternStatus, PatternType } from "./api";
import type { Lang } from "./i18n";

// Shared across the chart overlay badge, the Ideas "Chart Patterns" board, and /learn/patterns —
// one place for pattern display names so all three surfaces call the same shape by the same name.
export const PATTERN_LABEL: Record<PatternType, { en: string; bn: string }> = {
  ascending_triangle: { en: "Ascending Triangle", bn: "ঊর্ধ্বমুখী ত্রিভুজ" },
  descending_triangle: { en: "Descending Triangle", bn: "নিম্নমুখী ত্রিভুজ" },
  channel_up: { en: "Rising Channel", bn: "ঊর্ধ্বমুখী চ্যানেল" },
  channel_down: { en: "Falling Channel", bn: "নিম্নমুখী চ্যানেল" },
  channel_horizontal: { en: "Horizontal Channel", bn: "আনুভূমিক চ্যানেল" },
  double_top: { en: "Double Top", bn: "ডাবল টপ" },
  double_bottom: { en: "Double Bottom", bn: "ডাবল বটম" },
};

export const PATTERN_ORDER: PatternType[] = [
  "ascending_triangle",
  "descending_triangle",
  "channel_up",
  "channel_down",
  "channel_horizontal",
  "double_top",
  "double_bottom",
];

export const PATTERN_STATUS_LABEL: Record<PatternStatus, { en: string; bn: string }> = {
  forming: { en: "forming", bn: "গঠিত হচ্ছে" },
  confirmed_breakout_up: { en: "broke out up", bn: "উপরে ব্রেকআউট" },
  confirmed_breakout_down: { en: "broke out down", bn: "নিচে ব্রেকআউট" },
  invalidated: { en: "invalidated", bn: "ভেঙে গেছে" },
};

export function patternLabel(type: PatternType, lang: Lang): string {
  return lang === "bn" ? PATTERN_LABEL[type].bn : PATTERN_LABEL[type].en;
}

export function patternStatusLabel(status: PatternStatus, lang: Lang): string {
  return lang === "bn" ? PATTERN_STATUS_LABEL[status].bn : PATTERN_STATUS_LABEL[status].en;
}

// The chart_patterns screen's ScreenItem.note is always "{English pattern title} · {status}"
// (backend-generated, screener.py::_chart_patterns) — there's no dedicated pattern_type field on
// ScreenItem, so this is how the education pages match a board row back to its pattern type.
export function patternTypeFromNote(note: string | null | undefined): PatternType | null {
  if (!note) return null;
  return PATTERN_ORDER.find((type) => note.startsWith(PATTERN_LABEL[type].en)) ?? null;
}

export const PATTERN_LESSON_ID: Record<PatternType, string> = {
  ascending_triangle: "pattern_ascending_triangle",
  descending_triangle: "pattern_descending_triangle",
  channel_up: "pattern_channel_up",
  channel_down: "pattern_channel_down",
  channel_horizontal: "pattern_channel_horizontal",
  double_top: "pattern_double_top",
  double_bottom: "pattern_double_bottom",
};
