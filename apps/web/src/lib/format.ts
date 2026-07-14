export function formatOrdinal(input: number): string {
  const rounded = Math.round(input);
  const absolute = Math.abs(rounded);
  const lastTwo = absolute % 100;

  if (lastTwo >= 11 && lastTwo <= 13) return `${rounded}th`;

  const suffix =
    absolute % 10 === 1 ? "st" : absolute % 10 === 2 ? "nd" : absolute % 10 === 3 ? "rd" : "th";
  return `${rounded}${suffix}`;
}
