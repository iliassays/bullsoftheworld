import { type ReactNode, useEffect, useState } from "react";
import { api, ApiError, type Analytics } from "../lib/api";
import { taka } from "./ui";

// RSI is described, never acted on: 70+ "elevated", 30- "depressed", else "mid-range".
function rsiTag(rsi: number): { label: string; cls: string } {
  if (rsi >= 70) return { label: "elevated", cls: "text-down" };
  if (rsi <= 30) return { label: "depressed", cls: "text-up" };
  return { label: "mid-range", cls: "text-muted" };
}

// Trend stated as position vs moving averages — a fact, not a call.
function trendTag(a: Analytics): { label: string; cls: string } | null {
  if (a.above_sma_50 == null && a.above_sma_200 == null) return null;
  if (a.above_sma_50 && a.above_sma_200)
    return { label: "Above 50 & 200-day average", cls: "text-up bg-up/10" };
  if (a.above_sma_50 === false && a.above_sma_200 === false)
    return { label: "Below 50 & 200-day average", cls: "text-down bg-down/10" };
  return { label: "Mixed vs moving averages", cls: "text-muted bg-card" };
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
  const [a, setA] = useState<Analytics | null>(null);
  const [missing, setMissing] = useState(false);
  const [explanation, setExplanation] = useState("");
  const [explaining, setExplaining] = useState(false);
  const [explainErr, setExplainErr] = useState("");

  useEffect(() => {
    setA(null);
    setMissing(false);
    setExplanation("");
    setExplainErr("");
    api
      .analytics(code)
      .then(setA)
      .catch(() => setMissing(true));
  }, [code]);

  const explain = async () => {
    setExplaining(true);
    setExplainErr("");
    try {
      const r = await api.explainer(code);
      setExplanation(r.explanation);
    } catch (e) {
      setExplainErr(e instanceof ApiError ? e.detail : "Couldn't generate an explanation");
    } finally {
      setExplaining(false);
    }
  };

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
        <span className="text-accent font-semibold text-sm">📊 Technicals</span>
        <span className="ml-auto text-[10px] text-muted">as of {a.as_of_date} close</span>
      </div>

      {trend && (
        <div className={`mt-3 inline-block text-xs font-semibold px-3 py-1 rounded-full ${trend.cls}`}>
          {trend.label}
        </div>
      )}

      <div className="grid grid-cols-2 gap-2 mt-3">
        {rsi && (
          <Tile label="Momentum (RSI 14)">
            {rsiValue} <span className={`text-xs font-medium ${rsi.cls}`}>· {rsi.label}</span>
          </Tile>
        )}
        {a.relative_volume != null && (
          <Tile label="Volume vs 20-day">
            {a.relative_volume.toFixed(1)}×
          </Tile>
        )}
        {a.nearest_support != null && (
          <Tile label="Nearest support">
            <span className="text-up">{taka(a.nearest_support)}</span>
          </Tile>
        )}
        {a.nearest_resistance != null && (
          <Tile label="Nearest resistance">
            <span className="text-down">{taka(a.nearest_resistance)}</span>
          </Tile>
        )}
      </div>

      {pos != null && (
        <div className="mt-4">
          <div className="flex justify-between text-[10px] text-muted mb-1">
            <span>52-week range</span>
            {a.pct_from_52w_high != null && (
              <span className="tnum">{a.pct_from_52w_high.toFixed(1)}% from high</span>
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

      <div className="mt-4 border-t border-border pt-3">
        {!explanation && !explaining && (
          <button
            onClick={explain}
            className="text-sm text-accent font-semibold"
          >
            ✨ Explain these levels in plain language
          </button>
        )}
        {explaining && <p className="text-muted text-sm">Explaining the technicals…</p>}
        {explanation && (
          <p className="text-[15px] leading-relaxed text-text/90">{explanation}</p>
        )}
        {explainErr && <p className="text-down text-xs mt-1">{explainErr}</p>}
      </div>

      <p className="text-[10px] text-muted mt-3">
        Computed from end-of-day prices · descriptive, not advice.
      </p>
    </div>
  );
}
