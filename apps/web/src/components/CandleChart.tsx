import { useEffect, useRef, useState } from "react";
import { ColorType, LineStyle, createChart } from "lightweight-charts";
import { api, type Bar } from "../lib/api";

const COLORS = {
  ema9: "#f5b82e", // gold
  ema20: "#5b9cf5", // blue
  vwap: "#a78bfa", // purple
  support: "#16c784", // green
  resistance: "#ea3943", // red
};

function ema(values: number[], period: number): (number | null)[] {
  const out: (number | null)[] = new Array(values.length).fill(null);
  if (values.length < period) return out;
  const k = 2 / (period + 1);
  let e = values.slice(0, period).reduce((a, b) => a + b, 0) / period;
  out[period - 1] = e;
  for (let i = period; i < values.length; i++) {
    e = values[i] * k + e * (1 - k);
    out[i] = e;
  }
  return out;
}

function rollingVwap(bars: Bar[], period: number) {
  const pts: { time: string; value: number }[] = [];
  for (let i = period - 1; i < bars.length; i++) {
    let pv = 0;
    let v = 0;
    for (let j = i - period + 1; j <= i; j++) {
      const tp = (bars[j].high + bars[j].low + bars[j].close) / 3;
      pv += tp * bars[j].volume;
      v += bars[j].volume;
    }
    if (v > 0) pts.push({ time: bars[i].date, value: pv / v });
  }
  return pts;
}

function lineData(bars: Bar[], series: (number | null)[]) {
  return bars
    .map((b, i) => ({ time: b.date, value: series[i] }))
    .filter((p): p is { time: string; value: number } => p.value != null);
}

function Legend() {
  const items = [
    ["9 EMA", COLORS.ema9],
    ["20 EMA", COLORS.ema20],
    ["VWAP 20", COLORS.vwap],
    ["Support", COLORS.support],
    ["Resistance", COLORS.resistance],
  ] as const;
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1 px-1 pb-2">
      {items.map(([label, color]) => (
        <span key={label} className="flex items-center gap-1 text-[10px] text-muted">
          <span className="inline-block w-2.5 h-0.5 rounded" style={{ background: color }} />
          {label}
        </span>
      ))}
    </div>
  );
}

// Daily candlestick chart with 9/20 EMA, rolling VWAP, and support/resistance overlays.
export function CandleChart({ code }: { code: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [empty, setEmpty] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const chart = createChart(el, {
      autoSize: true,
      height: 300,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#8b97a6",
        attributionLogo: false,
      },
      grid: { vertLines: { color: "#1a2029" }, horzLines: { color: "#1a2029" } },
      rightPriceScale: { borderColor: "#232b36" },
      timeScale: { borderColor: "#232b36" },
      crosshair: { mode: 0 },
    });
    const candles = chart.addCandlestickSeries({
      upColor: "#16c784",
      downColor: "#ea3943",
      borderVisible: false,
      wickUpColor: "#16c784",
      wickDownColor: "#ea3943",
    });
    const overlay = (color: string) =>
      chart.addLineSeries({
        color,
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
    const ema9Series = overlay(COLORS.ema9);
    const ema20Series = overlay(COLORS.ema20);
    const vwapSeries = overlay(COLORS.vwap);

    let alive = true;
    Promise.all([api.bars(code, 180), api.analytics(code).catch(() => null)])
      .then(([bars, analytics]) => {
        if (!alive) return;
        if (!bars.length) return setEmpty(true);

        candles.setData(
          bars.map((b) => ({ time: b.date, open: b.open, high: b.high, low: b.low, close: b.close })),
        );
        const closes = bars.map((b) => b.close);
        ema9Series.setData(lineData(bars, ema(closes, 9)));
        ema20Series.setData(lineData(bars, ema(closes, 20)));
        vwapSeries.setData(rollingVwap(bars, 20));

        if (analytics?.nearest_support != null) {
          candles.createPriceLine({
            price: analytics.nearest_support,
            color: COLORS.support,
            lineWidth: 1,
            lineStyle: LineStyle.Dashed,
            axisLabelVisible: true,
            title: "S",
          });
        }
        if (analytics?.nearest_resistance != null) {
          candles.createPriceLine({
            price: analytics.nearest_resistance,
            color: COLORS.resistance,
            lineWidth: 1,
            lineStyle: LineStyle.Dashed,
            axisLabelVisible: true,
            title: "R",
          });
        }
        chart.timeScale().fitContent();
      })
      .catch(() => setEmpty(true));

    return () => {
      alive = false;
      chart.remove();
    };
  }, [code]);

  if (empty) {
    return <div className="text-muted text-sm py-6 text-center">No price history.</div>;
  }
  return (
    <div className="rounded-2xl border border-border bg-surface p-2">
      <Legend />
      <div ref={ref} className="w-full" />
    </div>
  );
}
