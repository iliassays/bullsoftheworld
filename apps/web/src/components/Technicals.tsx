import { type ReactNode, useEffect, useState } from "react";
import { api, type Analytics } from "../lib/api";
import { useLang } from "../lib/i18n";
import { taka } from "./ui";

// RSI is described, never acted on: 70+ "elevated", 30- "depressed", else "mid-range".
function rsiTag(rsi: number): { key: string; cls: string } {
  if (rsi >= 70) return { key: "rsi.elevated", cls: "text-down" };
  if (rsi <= 30) return { key: "rsi.depressed", cls: "text-up" };
  return { key: "rsi.mid", cls: "text-muted" };
}

// Trend stated as position vs moving averages — a fact, not a call.
function trendTag(a: Analytics): { key: string; cls: string } | null {
  if (a.above_sma_50 == null && a.above_sma_200 == null) return null;
  if (a.above_sma_50 && a.above_sma_200)
    return { key: "tech.aboveBoth", cls: "text-up bg-up/10" };
  if (a.above_sma_50 === false && a.above_sma_200 === false)
    return { key: "tech.belowBoth", cls: "text-down bg-down/10" };
  return { key: "tech.mixedMa", cls: "text-muted bg-card" };
}

function Tile({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="bg-card border border-border rounded-xl px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-muted">{label}</div>
      <div className="text-sm font-bold tnum mt-0.5">{children}</div>
    </div>
  );
}

export function Technicals({ code }: { code: string }) {
  const { t } = useLang();
  const [a, setA] = useState<Analytics | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    setA(null);
    setMissing(false);
    api
      .analytics(code)
      .then(setA)
      .catch(() => setMissing(true));
  }, [code]);

  if (missing) return null; // no history yet — stay quiet rather than show an empty shell
  if (!a) return null;

  const trend = trendTag(a);
  // Label from the rounded value shown, so "70" never reads as "mid-range".
  const rsiValue = a.rsi_14 != null ? Math.round(a.rsi_14) : null;
  const rsi = rsiValue != null ? rsiTag(rsiValue) : null;

  // Where today's close sits in the 52-week range (0 = low, 100 = high).
  const lo = a.week52_low;
  const hi = a.week52_high;
  const pos =
    lo != null && hi != null && hi > lo
      ? Math.min(100, Math.max(0, ((a.last_close - lo) / (hi - lo)) * 100))
      : null;

  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <div className="flex items-center">
        <span className="text-accent font-semibold text-sm">📊 {t("tech.title")}</span>
        <span className="ml-auto text-[10px] text-muted">
          {t("asOf")} {a.as_of_date} {t("close")}
        </span>
      </div>

      {trend && (
        <div className={`mt-3 inline-block text-xs font-semibold px-3 py-1 rounded-full ${trend.cls}`}>
          {t(trend.key)}
        </div>
      )}

      <div className="grid grid-cols-2 gap-2 mt-3">
        {rsi && (
          <Tile label={t("tech.momentum")}>
            {rsiValue} <span className={`text-xs font-medium ${rsi.cls}`}>· {t(rsi.key)}</span>
          </Tile>
        )}
        {a.relative_volume != null && (
          <Tile label={t("tech.volVs20")}>
            {a.relative_volume.toFixed(1)}×
          </Tile>
        )}
        {a.nearest_support != null && (
          <Tile label={t("tech.nearestSupport")}>
            <span className="text-up">{taka(a.nearest_support)}</span>
          </Tile>
        )}
        {a.nearest_resistance != null && (
          <Tile label={t("tech.nearestResistance")}>
            <span className="text-down">{taka(a.nearest_resistance)}</span>
          </Tile>
        )}
      </div>

      {pos != null && (
        <div className="mt-4">
          <div className="flex justify-between text-[10px] text-muted mb-1">
            <span>{t("range.52w")}</span>
            {a.pct_from_52w_high != null && (
              <span className="tnum">{a.pct_from_52w_high.toFixed(1)}% {t("tech.fromHigh")}</span>
            )}
          </div>
          <div className="relative h-1.5 rounded-full bg-card border border-border">
            <div
              className="absolute -top-[3px] w-2 h-2 rounded-full bg-accent shadow"
              style={{ left: `calc(${pos}% - 4px)` }}
            />
          </div>
          <div className="flex justify-between text-[11px] text-muted tnum mt-1">
            <span>{lo != null ? taka(lo) : "—"}</span>
            <span>{hi != null ? taka(hi) : "—"}</span>
          </div>
        </div>
      )}

      <p className="text-[10px] text-muted mt-3">{t("tech.footer")}</p>
    </div>
  );
}
