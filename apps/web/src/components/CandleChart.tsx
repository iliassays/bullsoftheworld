import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  ColorType,
  type IChartApi,
  type ISeriesApi,
  LineStyle,
  type SeriesMarker,
  type Time,
  createChart,
} from "lightweight-charts";
import { Link } from "../lib/nav";
import {
  api,
  type Bar,
  type PatternMatch,
  type PublicResearchChart,
  type ResearchConditionKey,
} from "../lib/api";
import { useLang } from "../lib/i18n";
import { patternLabel } from "../lib/patterns";
import { recentTransitions, researchChartCopy } from "../lib/research-chart";
import { researchConditionFromSearch } from "../lib/research-conditions";
import {
  ResearchConditionInspector,
  ResearchConditionTabs,
} from "./research-chart/ResearchConditionPanel";

const C = {
  up: "#2fbf71",
  down: "#f0564a",
  ema20: "#5b9cf5",
  ema50: "#a78bfa",
  pattern: "#e3b341",
  transition: "#e3b341",
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

function lineData(bars: Bar[], series: (number | null)[]) {
  return bars
    .map((b, i) => ({ time: b.date as Time, value: series[i] }))
    .filter((p): p is { time: Time; value: number } => p.value != null);
}

// Names the currently-active chart pattern (if any) and links to its plain-language lesson.
// Framework evidence, not backtested — see the lesson for why (a user asked for this after
// noticing patterns like this get shown elsewhere without saying whether they've been proven).
function PatternBadge({ pattern }: { pattern: PatternMatch }) {
  const { lang } = useLang();
  return (
    <Link
      to={`/learn/patterns/${pattern.pattern_type}`}
      className="flex items-center gap-1.5 mb-2 text-[11px] font-semibold bg-card border border-border rounded-full px-2.5 py-1 w-fit"
    >
      <span aria-hidden>📐</span>
      {lang === "bn" ? "সম্ভাব্য" : "Possible"} {patternLabel(pattern.pattern_type, lang)}
      <span className="font-normal text-muted">
        · {lang === "bn" ? "যাচাই না-করা কাঠামো" : "unvalidated framework"}
      </span>
    </Link>
  );
}

function Legend() {
  const { t } = useLang();
  const items: [string, string][] = [
    ["EMA20", C.ema20],
    ["EMA50", C.ema50],
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
  const { lang, t } = useLang();
  const [searchParams, setSearchParams] = useSearchParams();
  const copy = researchChartCopy(lang);
  const wrapRef = useRef<HTMLDivElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candlesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const barsRef = useRef<Bar[]>([]);
  const [empty, setEmpty] = useState(false);
  const [tf, setTf] = useState("3M");
  const [pattern, setPattern] = useState<PatternMatch | null>(null);
  const [research, setResearch] = useState<PublicResearchChart | null>();
  const [selectedCondition, setSelectedCondition] =
    useState<ResearchConditionKey>("trend_alignment");

  useEffect(() => {
    const requested = researchConditionFromSearch(searchParams.get("condition"));
    if (requested) setSelectedCondition(requested);
  }, [searchParams]);

  const selectCondition = (condition: ResearchConditionKey) => {
    setSelectedCondition(condition);
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.set("condition", condition);
      return next;
    }, { replace: true });
  };

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

    setEmpty(false);
    setResearch(undefined);
    setSelectedCondition("trend_alignment");

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
    candlesRef.current = candles;
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
    const ema20 = overlay(C.ema20);
    const ema50 = overlay(C.ema50);
    const patResistance = overlay(C.pattern);
    const patSupport = overlay(C.pattern);

    let alive = true;
    Promise.all([
      api.bars(code, 520),
      api.analytics(code).catch(() => null),
      api.researchChart(code).catch(() => null),
    ])
      .then(([bars, analytics, researchChart]) => {
        if (!alive) return;
        if (!bars.length) return setEmpty(true);
        barsRef.current = bars;
        setResearch(researchChart);

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
        const overlayData = (key: "ema20" | "ema50", fallbackPeriod: number) => {
          const registered = researchChart?.overlays.find((series) => series.key === key);
          return registered
            ? registered.points.map((point) => ({ time: point.date as Time, value: point.value }))
            : lineData(bars, ema(closes, fallbackPeriod));
        };
        ema20.setData(overlayData("ema20", 20));
        ema50.setData(overlayData("ema50", 50));

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
        // The single strongest currently-active chart pattern (framework evidence — see the
        // patterns lesson), drawn as trendlines/neckline on top of everything else above.
        const active = analytics?.patterns?.[0] ?? null;
        setPattern(active);
        if (active?.resistance_line) {
          patResistance.setData([
            { time: active.resistance_line.start.date as Time, value: active.resistance_line.start.price },
            { time: active.resistance_line.end.date as Time, value: active.resistance_line.end.price },
          ]);
        }
        if (active?.support_line) {
          patSupport.setData([
            { time: active.support_line.start.date as Time, value: active.support_line.start.price },
            { time: active.support_line.end.date as Time, value: active.support_line.end.price },
          ]);
        }
        if (active?.key_levels?.length) {
          for (const level of active.key_levels) {
            candles.createPriceLine({
              price: level,
              color: C.pattern,
              lineWidth: 1,
              lineStyle: LineStyle.Dashed,
              axisLabelVisible: true,
              title: "N",
            });
          }
        }
        applyTf("3M");
      })
      .catch(() => setEmpty(true));

    const resizeObserver = new ResizeObserver(() => {
      const tip = tipRef.current;
      if (!tip) return;
      tip.style.opacity = "0";
      tip.style.transform = "translate(8px, 8px)";
    });
    resizeObserver.observe(el);

    // Hover tooltip: date + OHLC. Measure it after writing the content so it
    // remains inside the plot on narrow screens and after viewport changes.
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
      const availableWidth = Math.max(0, el.clientWidth - 16);
      tip.style.maxWidth = `${availableWidth}px`;
      const tipWidth = Math.min(tip.offsetWidth, availableWidth);
      const x = Math.min(param.point.x + 12, el.clientWidth - tipWidth - 8);
      tip.style.transform = `translate(${Math.max(8, x)}px, 8px)`;
    });

    return () => {
      alive = false;
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      candlesRef.current = null;
      setPattern(null);
    };
  }, [code]);

  useEffect(() => {
    const candles = candlesRef.current;
    if (!candles || !research) return;
    const condition = research.conditions.find((item) => item.key === selectedCondition);
    if (!condition) {
      candles.setMarkers([]);
      return;
    }
    const markers: SeriesMarker<Time>[] = recentTransitions(condition).map((transition) => ({
      time: transition.date as Time,
      position: "belowBar",
      color: C.transition,
      shape: "circle",
      text: `${condition.short_label}${transition.sequence}`,
    }));
    candles.setMarkers(markers);
  }, [research, selectedCondition]);

  if (empty) {
    return <div className="text-muted text-sm py-6 text-center">{t("chart.noHistory")}</div>;
  }

  const activeCondition = research?.conditions.find((item) => item.key === selectedCondition);
  const latestPriceDate = barsRef.current.at(-1)?.date;
  const priceHasNewerBar = Boolean(
    research?.as_of_date && latestPriceDate && latestPriceDate > research.as_of_date,
  );

  return (
    <div className="rounded-2xl border border-border bg-surface p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-text">{copy.title}</h2>
          {research?.as_of_date && (
            <p className="mt-0.5 text-[10px] text-muted">
              {copy.dataThrough} {research.as_of_date} · {copy.completedClose}
            </p>
          )}
        </div>
        <div className="flex gap-1" aria-label="Chart range">
          {TIMEFRAMES.map((item) => (
            <button
              key={item.label}
              type="button"
              onClick={() => applyTf(item.label)}
              className={`cursor-pointer rounded-md px-2 py-1 text-[11px] font-semibold transition-colors ${
                tf === item.label ? "bg-accent text-bg" : "bg-card text-muted hover:text-text"
              }`}
            >
              {lang === "bn" && item.label === "All" ? "সব" : item.label}
            </button>
          ))}
        </div>
      </div>
      {pattern && <PatternBadge pattern={pattern} />}
      {research && (
        <div className="mt-3">
          <ResearchConditionTabs
            conditions={research.conditions}
            lang={lang}
            selected={selectedCondition}
            onSelect={selectCondition}
          />
        </div>
      )}
      {research === null && <p className="mt-3 text-xs text-warn">{copy.unavailable}</p>}
      <div ref={wrapRef} className="relative mt-2 overflow-hidden">
        <div data-chart className="w-full" />
        <div
          ref={tipRef}
          className="absolute top-0 left-0 pointer-events-none bg-bg/90 border border-border rounded-lg px-2 py-1 text-[11px] z-10 transition-opacity"
          style={{ opacity: 0 }}
        />
      </div>
      <Legend />
      {research && activeCondition && (
        <ResearchConditionInspector
          condition={activeCondition}
          lang={lang}
          research={research}
          priceHasNewerBar={priceHasNewerBar}
        />
      )}
    </div>
  );
}
