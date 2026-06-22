import type { ReactNode } from "react";

export const taka = (n: number) => `৳${n.toLocaleString("en-US", { minimumFractionDigits: 1 })}`;

export function Pct({ value }: { value: number }) {
  const up = value >= 0;
  return (
    <span className={`tnum ${up ? "text-up" : "text-down"}`}>
      {up ? "▲" : "▼"} {Math.abs(value).toFixed(2)}%
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

export function Avatar({ name }: { name: string }) {
  const initials = name
    .split(" ")
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
  return (
    <div className="w-9 h-9 rounded-full grid place-items-center font-bold text-sm text-accent bg-card shrink-0">
      {initials}
    </div>
  );
}

export function Spinner() {
  return <div className="text-muted text-sm py-8 text-center">Loading…</div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="text-muted text-sm py-10 text-center px-6">{children}</div>;
}
