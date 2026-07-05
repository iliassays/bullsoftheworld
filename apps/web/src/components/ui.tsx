import type { ReactNode } from "react";
import { useLang } from "../lib/i18n";

export const taka = (n: number) => `৳${n.toLocaleString("en-US", { minimumFractionDigits: 1 })}`;

// A bare "▲3.32%" is assumed to be the day's move — that's the default meaning everywhere on the
// site. `period="sinceBuy"` is the one case that actually needs a label: a portfolio holding's
// unrealized gain since average cost is NOT a daily figure, and showing it bare invites reading a
// 40% total gain as "up 40% today". (A prior "1d" label on every other % was removed after a user
// flagged it as confusing clutter — the freshness banner already covers "as of which close".)
export function Pct({ value, period }: { value: number; period?: "sinceBuy" }) {
  const { t } = useLang();
  const up = value >= 0;
  return (
    <span className={`tnum ${up ? "text-up" : "text-down"}`}>
      {up ? "▲" : "▼"} {Math.abs(value).toFixed(2)}%
      {period === "sinceBuy" && (
        <span className="text-muted font-normal text-[0.85em]"> {t("pct.sinceBuy")}</span>
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
