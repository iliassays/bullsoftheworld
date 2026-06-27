import { useLang } from "../lib/i18n";
import { taka } from "./ui";

// 52-week (or any) range bar with the current price marked — "where is it in its range" at a glance.
export function RangeBar({ low, high, value }: { low: number; high: number; value: number }) {
  const { t } = useLang();
  const span = high - low || 1;
  const pct = Math.max(0, Math.min(1, (value - low) / span));
  const where =
    pct >= 0.85 ? t("range.nearHigh") : pct <= 0.15 ? t("range.nearLow") : t("range.mid");
  return (
    <div className="mt-3 pt-3 border-t border-border">
      <div className="flex items-center justify-between text-[10px] text-muted mb-1">
        <span>{t("range.52w")}</span>
        <span>{where}</span>
      </div>
      <div className="relative h-1.5 rounded-full bg-gradient-to-r from-down/40 via-border to-up/40">
        <div
          className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-2.5 h-2.5 rounded-full bg-text border-2 border-surface"
          style={{ left: `${pct * 100}%` }}
        />
      </div>
      <div className="flex justify-between text-[10px] text-muted tnum mt-1">
        <span>{taka(low)}</span>
        <span className="text-text font-semibold">{taka(value)}</span>
        <span>{taka(high)}</span>
      </div>
    </div>
  );
}
