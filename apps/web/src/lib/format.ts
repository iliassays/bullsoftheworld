export function formatOrdinal(input: number): string {
  const rounded = Math.round(input);
  const absolute = Math.abs(rounded);
  const lastTwo = absolute % 100;

  if (lastTwo >= 11 && lastTwo <= 13) return `${rounded}th`;

  const suffix =
    absolute % 10 === 1 ? "st" : absolute % 10 === 2 ? "nd" : absolute % 10 === 3 ? "rd" : "th";
  return `${rounded}${suffix}`;
}

/** Compact an extreme quarter-over-quarter 13F percentage without changing its meaning. */
export function formatReportedShareChange(changePct: number): string {
  if (!Number.isFinite(changePct)) return "—";
  if (changePct < 1_000) {
    return `${changePct >= 0 ? "+" : ""}${changePct.toFixed(1)}%`;
  }

  const multiple = 1 + changePct / 100;
  if (multiple >= 1_000) return `${(multiple / 1_000).toFixed(1)}k×`;
  if (multiple >= 100) return `${multiple.toFixed(0)}×`;
  return `${multiple.toFixed(1)}×`;
}
