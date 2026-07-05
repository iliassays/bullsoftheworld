import type { ReactNode } from "react";
import { useLang } from "../lib/i18n";

export const taka = (n: number) => `৳${n.toLocaleString("en-US", { minimumFractionDigits: 1 })}`;

// `period` disambiguates what the % actually measures — a bare "▲3.32%" next to a stock is read
// differently depending on context (today's move? total gain since you bought it?), and a user
// asked for this explicitly after seeing an unlabeled % beside a valuation claim on a screener
// board. "1d" = intraday/EOD change since yesterday's close; "sinceBuy" = a portfolio holding's
// unrealized gain since average cost (NOT a daily figure — showing it bare invites exactly that
// misreading). Omit `period` only where the number isn't a price/holding move at all (e.g. a
// P/E-vs-sector ratio already labeled elsewhere).
export function Pct({ value, period }: { value: number; period?: "1d" | "sinceBuy" }) {
  const { t } = useLang();
  const up = value >= 0;
  return (
    <span className={`tnum ${up ? "text-up" : "text-down"}`}>
      {up ? "▲" : "▼"} {Math.abs(value).toFixed(2)}%
      {period && (
        <span className="text-muted font-normal text-[0.85em]">
          {" "}
          {t(period === "1d" ? "pct.1d" : "pct.sinceBuy")}
        </span>
      )}
    </span>
  );
}

export function SentimentTag({ s }: { s: "bull" | "bear" | null }) {
  if (!s) return null;
  const bull = s === "bull";
  return (
    <span
      className={`text-xs font-bold px-2 py-1 rounded-full ${
        bull ? "text-up bg-up/10" : "text-down bg-down/10"
      }`}
    >
      {bull ? "▲ Bull" : "▼ Bear"}
    </span>
  );
}

// `icon` (used by official desks) renders in place of the initials.
export function Avatar({ name, icon }: { name: string; icon?: ReactNode }) {
  const initials = name
    .split(" ")
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
  return (
    <div className="w-9 h-9 rounded-full grid place-items-center font-bold text-sm text-accent bg-card shrink-0">
      {icon ?? initials}
    </div>
  );
}

export function Spinner() {
  return <div className="text-muted text-sm py-8 text-center">Loading…</div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="text-muted text-sm py-10 text-center px-6">{children}</div>;
}

// Gold seal with a check — marks a verified official Bulls desk (agent) account.
export function VerifiedBadge({ size = 15 }: { size?: number }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      className="inline-block shrink-0 align-text-bottom"
      role="img"
      aria-label="Verified official desk"
    >
      <path
        fill="#e3b341"
        d="M12 1l2.6 1.9 3.2-.2 1 3 2.8 1.6-.9 3.1.9 3.1-2.8 1.6-1 3-3.2-.2L12 23l-2.6-1.9-3.2.2-1-3L2.4 15l.9-3.1L2.4 8.8l2.8-1.6 1-3 3.2.2z"
      />
      <path
        fill="#0d1524"
        d="M10.5 15.4l-2.9-2.9 1.3-1.3 1.6 1.6 4-4 1.3 1.3z"
      />
    </svg>
  );
}
