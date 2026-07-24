import { useEffect, useRef, useState } from "react";
import {
  ColorType,
  CrosshairMode,
  LineStyle,
  type SeriesMarker,
  type Time,
  createChart,
} from "lightweight-charts";

import type { SqueezePath } from "../../app/api-client";

const COLORS = {
  up: "#14835f",
  down: "#bd3e43",
  ema20: "#a76b00",
  ema50: "#5b6bb5",
  vwap: "#8a4fa8",
  trigger: "#14835f",
  invalidation: "#bd3e43",
};

const STATE_TEXT: Record<string, string> = {
  watch: "Watch",
  forming: "Forming",
  trigger_ready: "Trigger ready",
  confirmed: "Confirmed",
  exhausted: "Too extended",
  failed: "Failed",
};

interface Reading {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

export function SqueezeChart({ path }: { path: SqueezePath }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<Reading | null>(null);

  useEffect(() => {
    const element = containerRef.current;
    if (!element || path.points.length < 2) return;
    const styles = getComputedStyle(element);
    const text = styles.getPropertyValue("--text-muted").trim() || "#68717b";
    const border = styles.getPropertyValue("--border").trim() || "#e4e6e1";
    const chart = createChart(element, {
      autoSize: true,
      height: 320,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: text,
        attributionLogo: false,
        fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
        fontSize: 10,
      },
      grid: { vertLines: { color: border }, horzLines: { color: border } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: border, scaleMargins: { top: 0.08, bottom: 0.26 } },
      timeScale: { borderColor: border, fixLeftEdge: true, fixRightEdge: true, rightOffset: 3 },
      localization: { priceFormatter: (value: number) => value.toFixed(2) },
    });

    const candles = chart.addCandlestickSeries({
      upColor: COLORS.up,
      downColor: COLORS.down,
      borderVisible: false,
      wickUpColor: COLORS.up,
      wickDownColor: COLORS.down,
    });
    candles.setData(
      path.points.map((point) => ({
        time: point.date as Time,
        open: point.open,
        high: point.high,
        low: point.low,
        close: point.close,
      })),
    );

    // State transitions are the research story: when the setup was first seen and every time
    // the taxonomy re-classified it.
    const markers: SeriesMarker<Time>[] = path.stateHistory.map((change) => ({
      time: change.date as Time,
      position: change.state === "failed" || change.state === "exhausted" ? "aboveBar" : "belowBar",
      color:
        change.state === "confirmed"
          ? COLORS.up
          : change.state === "failed" || change.state === "exhausted"
            ? COLORS.down
            : COLORS.ema20,
      shape:
        change.state === "failed" || change.state === "exhausted" ? "arrowDown" : "arrowUp",
      text: STATE_TEXT[change.state] ?? change.state,
    }));
    candles.setMarkers(
      markers.sort((left, right) => String(left.time).localeCompare(String(right.time))),
    );

    const overlay = (
      key: "ema20" | "ema50" | "anchoredVwap",
      color: string,
      style: LineStyle,
    ) => {
      const data = path.points
        .filter((point) => point[key] !== null)
        .map((point) => ({ time: point.date as Time, value: point[key] as number }));
      if (data.length < 2) return;
      const series = chart.addLineSeries({
        color,
        lineWidth: 1,
        lineStyle: style,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      series.setData(data);
    };
    overlay("ema20", COLORS.ema20, LineStyle.Solid);
    overlay("ema50", COLORS.ema50, LineStyle.Solid);
    overlay("anchoredVwap", COLORS.vwap, LineStyle.Dashed);

    const level = (price: number | null, color: string, title: string, style: LineStyle) => {
      if (price === null) return;
      candles.createPriceLine({
        price,
        color,
        lineWidth: 1,
        lineStyle: style,
        axisLabelVisible: true,
        title,
      });
    };
    // Only operational levels are drawn: the trigger is where the setup activates and the
    // invalidation is where it dies. The 2R objective is derived arithmetic reported in the
    // metrics — drawing it as a chart line reads as a price forecast, and it frequently sits
    // outside the autoscaled range anyway, so the line would be invisible as often as not.
    level(path.entry.triggerPrice, COLORS.trigger, "Trigger", LineStyle.Dashed);
    level(path.entry.invalidationPrice, COLORS.invalidation, "Invalidation", LineStyle.Dashed);

    const volume = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
      lastValueVisible: false,
      priceLineVisible: false,
    });
    chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    volume.setData(
      path.points.map((point) => ({
        time: point.date as Time,
        value: point.volume,
        color:
          point.close >= point.open ? "rgba(20, 131, 95, 0.28)" : "rgba(189, 62, 67, 0.25)",
      })),
    );

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
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [path]);

  const latest = path.points.at(-1);
  const reading =
    hover ??
    (latest
      ? {
          date: latest.date,
          open: latest.open,
          high: latest.high,
          low: latest.low,
          close: latest.close,
        }
      : null);

  return (
    <div className="squeeze-chart">
      <div className="squeeze-chart__reading" aria-live="polite">
        <span>{reading?.date ?? "No completed prices"}</span>
        {reading && (
          <span className="squeeze-chart__ohlc">
            <b>O</b> {reading.open.toFixed(2)} <b>H</b> {reading.high.toFixed(2)} <b>L</b>{" "}
            {reading.low.toFixed(2)} <b>C</b> {reading.close.toFixed(2)}
          </span>
        )}
        {path.atrChangePct !== null && (
          <span
            className={path.atrChangePct <= 0 ? "value-up" : "value-down"}
            title="14-session ATR now versus 20 sessions earlier"
          >
            ATR {path.atrChangePct >= 0 ? "+" : ""}
            {path.atrChangePct.toFixed(1)}%
          </span>
        )}
      </div>
      <div
        aria-label={`${path.entry.code} daily candles with EMA and anchored VWAP overlays`}
        ref={containerRef}
      />
      <div className="squeeze-chart__legend">
        <span><i style={{ background: COLORS.ema20 }} />EMA 20</span>
        <span><i style={{ background: COLORS.ema50 }} />EMA 50</span>
        <span><i style={{ background: COLORS.vwap }} />Anchored VWAP</span>
        <span><i style={{ background: COLORS.trigger }} />Trigger</span>
        <span><i style={{ background: COLORS.invalidation }} />Invalidation</span>
      </div>
      <p className="squeeze-chart__basis">
        {path.priceBasis} {path.overlayBasis}
      </p>
    </div>
  );
}
