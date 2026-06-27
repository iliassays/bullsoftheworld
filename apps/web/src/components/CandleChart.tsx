import { useEffect, useRef, useState } from "react";
import {
  ColorType,
  type IChartApi,
  LineStyle,
  type Time,
  createChart,
} from "lightweight-charts";
import { api, type Bar } from "../lib/api";
import { useLang } from "../lib/i18n";

const C = {
  up: "#16c784",
  down: "#ea3943",
  ema9: "#f5b82e",
  ema20: "#5b9cf5",
  vwap: "#a78bfa",
  grid: "#161b22",
  axis: "#232b36",
  text: "#8b97a6",
};

const TIMEFRAMES = [
  { label: "1M", bars: 22 },
  { label: "3M", bars: 66 },
  { label: "6M", bars: 132 },
  { label: "1Y", bars: 250 },
  { label: "All", bars: 9999 },
] as const;

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
  const pts: { time: Time; value: number }[] = [];
  for (let i = period - 1; i < bars.length; i++) {
    let pv = 0;
    let v = 0;
    for (let j = i - period + 1; j <= i; j++) {
      const tp = (bars[j].high + bars[j].low + bars[j].close) / 3;
      pv += tp * bars[j].volume;
      v += bars[j].volume;
    }
    if (v > 0) pts.push({ time: bars[i].date as Time, value: pv / v });
  }
  return pts;
}

function lineData(bars: Bar[], series: (number | null)[]) {
  return bars
    .map((b, i) => ({ time: b.date as Time, value: series[i] }))
    .filter((p): p is { time: Time; value: number } => p.value != null);
}

function Legend() {
  const { t } = useLang();
  const items: [string, string][] = [
    ["9 EMA", C.ema9],
    ["20 EMA", C.ema20],
    ["VWAP", C.vwap],
    [t("chart.support"), C.up],
    [t("chart.resistance"), C.down],
  ];
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2">
      {items.map(([label, color]) => (
        <span key={label} className="flex items-center gap-1 text-[10px] text-muted">
          <span className="inline-block w-2.5 h-0.5 rounded" style={{ background: color }} />
          {label}
        </span>
      ))}
    </div>
  );
}

export function CandleChart({ code }: { code: string }) {
  const { t } = useLang();
  const wrapRef = useRef<HTMLDivElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const barsRef = useRef<Bar[]>([]);
  const [empty, setEmpty] = useState(false);
  const [tf, setTf] = useState("3M");

  // Apply a timeframe by zooming the visible range (indicators stay computed on full history).
  const applyTf = (label: string) => {
    setTf(label);
    const bars = barsRef.current;
    const chart = chartRef.current;
    if (!bars.length || !chart) return;
    const n = TIMEFRAMES.find((t) => t.label === label)?.bars ?? 66;
    const from = bars[Math.max(0, bars.length - n)].date as Time;
    const to = bars[bars.length - 1].date as Time;
    chart.timeScale().setVisibleRange({ from, to });
  };

  useEffect(() => {
    const el = wrapRef.current?.querySelector<HTMLDivElement>("[data-chart]");
    if (!el) return;

    const chart = createChart(el, {
      autoSize: true,
      height: 340,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: C.text,
        attributionLogo: false,
        fontSize: 11,
      },
      grid: { vertLines: { color: C.grid }, horzLines: { color: C.grid } },
      rightPriceScale: { borderColor: C.axis, scaleMargins: { top: 0.08, bottom: 0.28 } },
      timeScale: { borderColor: C.axis, rightOffset: 4 },
      crosshair: { mode: 1 },
    });
    chartRef.current = chart;

    const candles = chart.addCandlestickSeries({
      upColor: C.up,
      downColor: C.down,
      borderVisible: false,
      wickUpColor: C.up,
      wickDownColor: C.down,
    });
    const volume = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "vol",
    });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });

    const overlay = (color: string, dashed = false) =>
      chart.addLineSeries({
        color,
        lineWidth: 2,
        lineStyle: dashed ? LineStyle.Dotted : LineStyle.Solid,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
    const ema9 = overlay(C.ema9);
    const ema20 = overlay(C.ema20);
    const vwap = overlay(C.vwap, true);

    let alive = true;
    Promise.all([api.bars(code, 300), api.analytics(code).catch(() => null)])
      .then(([bars, analytics]) => {
        if (!alive) return;
        if (!bars.length) return setEmpty(true);
        barsRef.current = bars;

        candles.setData(
          bars.map((b) => ({ time: b.date as Time, open: b.open, high: b.high, low: b.low, close: b.close })),
        );
        volume.setData(
          bars.map((b) => ({
            time: b.date as Time,
            value: b.volume,
            color: b.close >= b.open ? "rgba(22,199,132,0.35)" : "rgba(234,57,67,0.35)",
          })),
        );
        const closes = bars.map((b) => b.close);
        ema9.setData(lineData(bars, ema(closes, 9)));
        ema20.setData(lineData(bars, ema(closes, 20)));
        vwap.setData(rollingVwap(bars, 20));

        if (analytics?.nearest_support != null) {
          candles.createPriceLine({
            price: analytics.nearest_support,
            color: C.up,
            lineWidth: 1,
            lineStyle: LineStyle.Dashed,
            axisLabelVisible: true,
            title: "S",
          });
        }
        if (analytics?.nearest_resistance != null) {
          candles.createPriceLine({
            price: analytics.nearest_resistance,
            color: C.down,
            lineWidth: 1,
            lineStyle: LineStyle.Dashed,
            axisLabelVisible: true,
            title: "R",
          });
        }
        // Mark where the recent swing high / low formed (the structure behind S/R).
        const markers = [];
        if (analytics?.recent_swing_high) {
          markers.push({
            time: analytics.recent_swing_high.date as Time,
            position: "aboveBar" as const,
            color: C.down,
            shape: "arrowDown" as const,
            text: "SH",
          });
        }
        if (analytics?.recent_swing_low) {
          markers.push({
            time: analytics.recent_swing_low.date as Time,
            position: "belowBar" as const,
            color: C.up,
            shape: "arrowUp" as const,
            text: "SL",
          });
        }
        if (markers.length) candles.setMarkers(markers.sort((a, b) => (a.time < b.time ? -1 : 1)));

        applyTf("3M");
      })
      .catch(() => setEmpty(true));

    // Hover tooltip: date + OHLC.
    chart.subscribeCrosshairMove((param) => {
      const tip = tipRef.current;
      if (!tip) return;
      const c = param.seriesData.get(candles) as
        | { open: number; high: number; low: number; close: number }
        | undefined;
      if (!param.time || !param.point || !c) {
        tip.style.opacity = "0";
        return;
      }
      const up = c.close >= c.open;
      tip.innerHTML =
        `<div style="color:${C.text};font-size:10px">${param.time}</div>` +
        `<div style="font-variant-numeric:tabular-nums">O ${c.open} H ${c.high} L ${c.low} ` +
        `<span style="color:${up ? C.up : C.down};font-weight:700">C ${c.close}</span></div>`;
      tip.style.opacity = "1";
      const x = Math.min(param.point.x + 12, el.clientWidth - 150);
      tip.style.transform = `translate(${Math.max(8, x)}px, 8px)`;
    });

    return () => {
      alive = false;
      chart.remove();
      chartRef.current = null;
    };
  }, [code]);

  if (empty) {
    return <div className="text-muted text-sm py-6 text-center">{t("chart.noHistory")}</div>;
  }

  return (
    <div className="rounded-2xl border border-border bg-surface p-3">
      <div className="flex justify-end gap-1">
        {TIMEFRAMES.map((t) => (
          <button
            key={t.label}
            onClick={() => applyTf(t.label)}
            className={`text-[11px] px-2 py-0.5 rounded-md font-semibold ${
              tf === t.label ? "bg-accent text-bg" : "text-muted bg-card"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div ref={wrapRef} className="relative mt-2">
        <div data-chart className="w-full" />
        <div
          ref={tipRef}
          className="absolute top-0 left-0 pointer-events-none bg-bg/90 border border-border rounded-lg px-2 py-1 text-[11px] z-10 transition-opacity"
          style={{ opacity: 0 }}
        />
      </div>
      <Legend />
    </div>
  );
}
