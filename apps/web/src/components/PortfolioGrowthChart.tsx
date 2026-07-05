import { useEffect, useRef, useState } from "react";
import { ColorType, type Time, createChart } from "lightweight-charts";
import { api, type PortfolioHistoryPeriod } from "../lib/api";
import { useLang } from "../lib/i18n";
import { taka } from "./ui";

const C = {
  up: "#2fbf71",
  down: "#f0564a",
  grid: "#161b22",
  axis: "#232b36",
  text: "#8b97a6",
};

const PERIODS: PortfolioHistoryPeriod[] = ["1w", "1m", "3m", "6m", "1y", "all"];
const PERIOD_LABEL: Record<PortfolioHistoryPeriod, string> = {
  "1w": "1W",
  "1m": "1M",
  "3m": "3M",
  "6m": "6M",
  "1y": "1Y",
  all: "All",
};

// Growth-over-time — the AGGREGATE snapshot the daily ingestion job writes (see
// ingestion.portfolio_snapshot), never reconstructed from current holdings retroactively: a
// holding's quantity/avg_cost can change at any time, so projecting it backward would show a
// fictional "what if you always held this" line. History starts the day tracking began — a new
// account (or a fresh deploy of this feature) has nothing to plot yet, which is the honest state.
export function PortfolioGrowthChart() {
  const { t } = useLang();
  const wrapRef = useRef<HTMLDivElement>(null);
  const [period, setPeriod] = useState<PortfolioHistoryPeriod>("3m");
  const [points, setPoints] = useState<{ date: string; total_value: number }[] | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .portfolioHistory(period)
      .then((rows) => {
        if (!alive) return;
        setPoints(
          rows
            .filter((r): r is { date: string; total_value: number; total_cost: number } => r.total_value != null)
            .map((r) => ({ date: r.date, total_value: r.total_value })),
        );
      })
      .catch(() => alive && setPoints([]));
    return () => {
      alive = false;
    };
  }, [period]);

  useEffect(() => {
    const el = wrapRef.current?.querySelector<HTMLDivElement>("[data-growth-chart]");
    if (!el || !points || points.length < 2) return;

    const up = points[points.length - 1].total_value >= points[0].total_value;
    const color = up ? C.up : C.down;
    const chart = createChart(el, {
      autoSize: true,
      height: 160,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: C.text,
        attributionLogo: false,
        fontSize: 10,
      },
      grid: { vertLines: { visible: false }, horzLines: { color: C.grid } },
      rightPriceScale: { borderColor: C.axis },
      timeScale: { borderColor: C.axis, rightOffset: 2 },
      crosshair: { mode: 1 },
      handleScroll: false,
      handleScale: false,
    });
    const series = chart.addAreaSeries({
      lineColor: color,
      topColor: `${color}33`,
      bottomColor: `${color}03`,
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
    });
    series.setData(points.map((p) => ({ time: p.date as Time, value: p.total_value })));
    chart.timeScale().fitContent();

    return () => chart.remove();
  }, [points]);

  // Fewer than 2 points means first === last (or nothing) — a "+0.0%" there would read as flat
  // performance, not "not enough data yet". Gate on length, not just null-ness.
  const enoughPoints = points != null && points.length >= 2;
  const first = enoughPoints ? points[0].total_value : null;
  const last = enoughPoints ? points[points.length - 1].total_value : null;
  const delta = first != null && last != null ? last - first : null;
  const deltaPct = first != null && last != null && first ? (delta! / first) * 100 : null;

  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <div className="flex items-center justify-between">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">
          {t("pf.growthTitle")}
        </div>
        {delta != null && deltaPct != null && (
          <div className={`text-sm font-bold tnum ${delta >= 0 ? "text-up" : "text-down"}`}>
            {delta >= 0 ? "+" : ""}
            {taka(delta)} ({delta >= 0 ? "+" : ""}
            {deltaPct.toFixed(1)}%)
          </div>
        )}
      </div>

      {points === null ? (
        <div className="h-40" />
      ) : points.length < 2 ? (
        <div className="py-8 text-center">
          <div className="text-2xl">🌱</div>
          <p className="text-sm text-muted mt-2 leading-relaxed">{t("pf.growthBuilding")}</p>
        </div>
      ) : (
        <div ref={wrapRef} className="mt-2">
          <div data-growth-chart className="w-full" />
        </div>
      )}

      <div className="flex gap-1.5 mt-3 justify-center">
        {PERIODS.map((p) => (
          <button
            key={p}
            onClick={() => setPeriod(p)}
            className={`text-[11px] px-2.5 py-1 rounded-md font-semibold ${
              period === p ? "bg-accent text-bg" : "text-muted bg-card"
            }`}
          >
            {PERIOD_LABEL[p]}
          </button>
        ))}
      </div>
    </div>
  );
}
