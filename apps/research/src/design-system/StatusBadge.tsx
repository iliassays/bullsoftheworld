import type { ReactNode } from "react";

export type StatusTone = "neutral" | "positive" | "warning" | "negative" | "info" | "violet";

export function StatusBadge({
  children,
  tone = "neutral",
  dot = false,
}: {
  children: ReactNode;
  tone?: StatusTone;
  dot?: boolean;
}) {
  return (
    <span className={`ds-status ds-status--${tone}`}>
      {dot && <span aria-hidden="true" className="ds-status__dot" />}
      {children}
    </span>
  );
}
