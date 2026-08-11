import { useEffect, useMemo, useRef, useState } from "react";
import {
  ColorType,
  CrosshairMode,
  LineStyle,
  type SeriesMarker,
  type Time,
  createChart,
} from "lightweight-charts";

import type { DecisionEvent } from "../../app/api-client";
import type { ResearchEvidenceItem } from "../research-queue/model";
import type {
  DossierOverlaySeries,
  DossierPricePoint,
  ResearchConditionEvaluation,
} from "./model";
import type { DossierChartMode, DossierChartRange } from "./research-condition";

interface DossierChartProps {
  points: readonly DossierPricePoint[];
  benchmarkCode: string;
  decisionEvents: readonly DecisionEvent[];
  evidence: readonly ResearchEvidenceItem[];
  overlays: readonly DossierOverlaySeries[];
  selectedCondition: ResearchConditionEvaluation;
  mode: DossierChartMode;
  range: DossierChartRange;
  onModeChange: (mode: DossierChartMode) => void;
  onRangeChange: (range: DossierChartRange) => void;
  support: number | null;
  resistance: number | null;
  averageCost: number | null;
}

interface HoverReading {
  date: string;
  open?: number;
  high?: number;
  low?: number;
  close?: number;
  stockRelative?: number;
  benchmarkRelative?: number;
}

const RANGE_SESSIONS: Record<DossierChartRange, number> = {
  "3M": 66,
  "6M": 132,
  "1Y": 252,
};

const COLORS = {
  up: "#14835f",
  down: "#bd3e43",
  accent: "#a76b00",
  benchmark: "#68717b",
  ma20: "#2d6f9d",
  ma50: "#8366a3",
  condition: "#a76b00",
  evidence: "#2d6f9d",
  grid: "#e4e6e1",
  axis: "#cfd3ce",
  text: "#68717b",
};

function eventMarker(event: DecisionEvent): SeriesMarker<Time> | null {
  const time = event.effectiveDate as Time;
  if (event.eventType === "target") {
    const action = String(event.payload.action ?? "target");
    const isExit = action === "exit" || action === "reduce";
    return {
      time,
      position: isExit ? "aboveBar" : "belowBar",
      color: isExit ? COLORS.down : COLORS.accent,
      shape: isExit ? "arrowDown" : "arrowUp",
      text: action === "entry" ? "Target" : action,
    };
  }
  if (event.eventType === "fill") {
    const side = String(event.payload.side ?? "");
    const isSell = side === "sell";
    return {
      time,
      position: isSell ? "aboveBar" : "belowBar",
      color: isSell ? COLORS.down : COLORS.up,
      shape: isSell ? "arrowDown" : "arrowUp",
      text: "Fill",
    };
  }
  if (event.eventType === "risk" || event.eventType === "rejection") {
    return {
      time,
      position: "aboveBar",
      color: COLORS.down,
      shape: "circle",
      text: event.eventType === "rejection" ? "Blocked" : "Risk",
    };
  }
  return null;
}

export function buildConditionMarkers(
  availableDates: readonly string[],
  condition: ResearchConditionEvaluation,
): SeriesMarker<Time>[] {
  const dates = new Set(availableDates);
  return condition.transitions
    .filter((transition) => dates.has(transition.date))
    .slice(-12)
    .map((transition) => ({
      time: transition.date as Time,
      position: "belowBar",
      color: COLORS.condition,
      shape: "circle",
      text: `${condition.shortLabel}${transition.sequence}`,
    }));
}

function chartMarkers(
  availableDates: readonly string[],
  events: readonly DecisionEvent[],
  evidence: readonly ResearchEvidenceItem[],
  condition: ResearchConditionEvaluation,
): SeriesMarker<Time>[] {
  const dates = new Set(availableDates);
  const markers = events
    .filter((event) => dates.has(event.effectiveDate))
    .flatMap((event) => {
      const marker = eventMarker(event);
      return marker ? [marker] : [];
    });
  const evidenceMarkers = evidence
    .map((item) => item.publishedAt.slice(0, 10))
    .map((publishedAt) => availableDates.find((date) => date >= publishedAt))
    .filter((date): date is string => Boolean(date))
    .filter((date, index, all) => all.indexOf(date) === index)
    .map<SeriesMarker<Time>>((date) => ({
      time: date as Time,
      position: "aboveBar",
      color: COLORS.evidence,
      shape: "square",
      text: "E",
    }));
  return [...markers, ...evidenceMarkers, ...buildConditionMarkers(availableDates, condition)].sort((left, right) =>
    String(left.time).localeCompare(String(right.time)),
  );
}

export function DossierChart({
  points,
  benchmarkCode,
  decisionEvents,
  evidence,
  overlays,
  selectedCondition,
  mode,
  range,
  onModeChange,
  onRangeChange,
  support,
  resistance,
  averageCost,
}: DossierChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<HoverReading | null>(null);
  const [themeRevision, setThemeRevision] = useState(0);
  const visiblePoints = useMemo(
    () => points.slice(-RANGE_SESSIONS[range]),
    [points, range],
  );

  useEffect(() => {
    const observer = new MutationObserver(() => setThemeRevision((value) => value + 1));
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const element = containerRef.current;
    if (!element || visiblePoints.length < 2) return;
    const styles = getComputedStyle(element);
    const chartColors = {
      ...COLORS,
      benchmark: styles.getPropertyValue("--text-muted").trim() || COLORS.benchmark,
      grid: styles.getPropertyValue("--border").trim() || COLORS.grid,
      axis: styles.getPropertyValue("--border-strong").trim() || COLORS.axis,
      text: styles.getPropertyValue("--text-muted").trim() || COLORS.text,
    };

    const chart = createChart(element, {
      autoSize: true,
      height: 390,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: chartColors.text,
        attributionLogo: false,
        fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: chartColors.grid },
        horzLines: { color: chartColors.grid },
      },
      rightPriceScale: {
        borderColor: chartColors.axis,
        scaleMargins: { top: 0.08, bottom: mode === "price" ? 0.25 : 0.08 },
      },
      timeScale: {
        borderColor: chartColors.axis,
        rightOffset: 3,
        fixLeftEdge: true,
        fixRightEdge: true,
      },
      crosshair: { mode: CrosshairMode.Normal },
      localization: { priceFormatter: (price: number) => price.toFixed(2) },
    });

    const markers = chartMarkers(
      visiblePoints.map((point) => point.date),
      decisionEvents,
      evidence,
      selectedCondition,
    );
    if (mode === "price") {
      const candles = chart.addCandlestickSeries({
        upColor: COLORS.up,
        downColor: COLORS.down,
        borderVisible: false,
        wickUpColor: COLORS.up,
        wickDownColor: COLORS.down,
      });
      candles.setData(
        visiblePoints.map((point) => ({
          time: point.date as Time,
          open: point.open,
          high: point.high,
          low: point.low,
          close: point.close,
        })),
      );
      candles.setMarkers(markers);

      const volume = chart.addHistogramSeries({
        priceFormat: { type: "volume" },
        priceScaleId: "volume",
        lastValueVisible: false,
        priceLineVisible: false,
      });
      chart.priceScale("volume").applyOptions({
        scaleMargins: { top: 0.82, bottom: 0 },
      });
      volume.setData(
        visiblePoints.map((point) => ({
          time: point.date as Time,
          value: point.volume,
          color: point.close >= point.open
            ? "rgba(20, 131, 95, 0.28)"
            : "rgba(189, 62, 67, 0.25)",
        })),
      );

      const addOverlay = (overlay: DossierOverlaySeries | undefined, color: string) => {
        if (!overlay) return;
        const series = chart.addLineSeries({
          color,
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        });
        const firstDate = visiblePoints[0]!.date;
        const lastDate = visiblePoints[visiblePoints.length - 1]!.date;
        series.setData(
          overlay.points
            .filter((point) => point.date >= firstDate && point.date <= lastDate)
            .map((point) => ({ time: point.date as Time, value: point.value })),
        );
      };
      addOverlay(overlays.find((overlay) => overlay.key === "ema20"), COLORS.ma20);
      addOverlay(overlays.find((overlay) => overlay.key === "ema50"), COLORS.ma50);

      if (support !== null) {
        candles.createPriceLine({
          price: support,
          color: COLORS.up,
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: "Support",
        });
      }
      if (resistance !== null) {
        candles.createPriceLine({
          price: resistance,
          color: COLORS.down,
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: "Resistance",
        });
      }
      if (averageCost !== null) {
        candles.createPriceLine({
          price: averageCost,
          color: COLORS.accent,
          lineWidth: 1,
          lineStyle: LineStyle.Dotted,
          axisLabelVisible: true,
          title: "Avg cost",
        });
      }

      chart.subscribeCrosshairMove((parameter) => {
        const reading = parameter.seriesData.get(candles) as
          | { open: number; high: number; low: number; close: number }
          | undefined;
        if (!parameter.time || !reading) {
          setHover(null);
          return;
        }
        setHover({ date: String(parameter.time), ...reading });
      });
    } else {
      const base = visiblePoints.find((point) => point.benchmarkClose !== null);
      if (base?.benchmarkClose !== null && base?.benchmarkClose !== undefined) {
        const stock = chart.addLineSeries({
          color: COLORS.up,
          lineWidth: 2,
          title: "Security",
          priceFormat: { type: "percent" },
        });
        const benchmark = chart.addLineSeries({
          color: chartColors.benchmark,
          lineWidth: 2,
          lineStyle: LineStyle.Dashed,
          title: benchmarkCode,
          priceFormat: { type: "percent" },
        });
        const relative = visiblePoints
          .filter((point) => point.benchmarkClose !== null)
          .map((point) => ({
            time: point.date as Time,
            stock: (point.close / base.close - 1) * 100,
            benchmark: (point.benchmarkClose! / base.benchmarkClose! - 1) * 100,
          }));
        stock.setData(relative.map((point) => ({ time: point.time, value: point.stock })));
        benchmark.setData(
          relative.map((point) => ({ time: point.time, value: point.benchmark })),
        );
        stock.setMarkers(markers);
        chart.subscribeCrosshairMove((parameter) => {
          const stockReading = parameter.seriesData.get(stock) as { value: number } | undefined;
          const benchmarkReading = parameter.seriesData.get(benchmark) as
            | { value: number }
            | undefined;
          if (!parameter.time || !stockReading) {
            setHover(null);
            return;
          }
          setHover({
            date: String(parameter.time),
            stockRelative: stockReading.value,
            benchmarkRelative: benchmarkReading?.value,
          });
        });
      }
    }

    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [
    averageCost,
    benchmarkCode,
    decisionEvents,
    evidence,
    mode,
    overlays,
    resistance,
    selectedCondition,
    support,
    themeRevision,
    visiblePoints,
  ]);

  if (points.length < 2) {
    return <div className="dossier-chart--empty">Price history is not available at this cutoff.</div>;
  }

  const latest = visiblePoints[visiblePoints.length - 1]!;
  return (
    <div className="dossier-chart">
      <div className="dossier-chart__toolbar">
        <div aria-label="Chart mode" className="dossier-chart__segments">
          <button
            aria-pressed={mode === "price"}
            onClick={() => onModeChange("price")}
            type="button"
          >
            Price
          </button>
          <button
            aria-pressed={mode === "relative"}
            onClick={() => onModeChange("relative")}
            type="button"
          >
            Relative to {benchmarkCode}
          </button>
        </div>
        <div aria-label="Chart range" className="dossier-chart__segments">
          {(Object.keys(RANGE_SESSIONS) as DossierChartRange[]).map((item) => (
            <button
              aria-pressed={range === item}
              key={item}
              onClick={() => onRangeChange(item)}
              type="button"
            >
              {item}
            </button>
          ))}
        </div>
      </div>
      <div className="dossier-chart__legend" aria-live="polite">
        {hover ? (
          mode === "price" ? (
            <>
              <strong>{hover.date}</strong>
              <span>O {hover.open?.toFixed(2)}</span>
              <span>H {hover.high?.toFixed(2)}</span>
              <span>L {hover.low?.toFixed(2)}</span>
              <span>C {hover.close?.toFixed(2)}</span>
            </>
          ) : (
            <>
              <strong>{hover.date}</strong>
              <span>Security {hover.stockRelative?.toFixed(2)}%</span>
              <span>{benchmarkCode} {hover.benchmarkRelative?.toFixed(2)}%</span>
            </>
          )
        ) : (
          <>
            <strong>{latest.date}</strong>
            <span>Close {latest.close.toFixed(2)}</span>
            <span>{mode === "price" ? "EMA20 / EMA50 · completed sessions" : "Indexed return from range start"}</span>
          </>
        )}
      </div>
      <div className="dossier-chart__canvas" ref={containerRef} />
      <div className="dossier-chart__key">
        {mode === "price" ? (
          <>
            <span><i style={{ background: COLORS.ma20 }} />EMA20 · backend</span>
            <span><i style={{ background: COLORS.ma50 }} />EMA50 · backend</span>
            <span><i style={{ background: COLORS.condition }} />{selectedCondition.shortLabel}# · {selectedCondition.title}</span>
            <span><i style={{ background: COLORS.evidence }} />Official evidence</span>
            <span><i style={{ background: COLORS.accent }} />Portfolio target / cost</span>
          </>
        ) : (
          <>
            <span><i style={{ background: COLORS.up }} />Security</span>
            <span><i style={{ background: COLORS.benchmark }} />{benchmarkCode}</span>
          </>
        )}
      </div>
    </div>
  );
}
