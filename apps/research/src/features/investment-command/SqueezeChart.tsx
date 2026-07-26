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
  discovery: "#1f6feb",
  priorEpisode: "#68717b",
};

const STATE_MARKER: Record<string, string> = {
  trigger_ready: "T",
  confirmed: "C",
  exhausted: "X",
  failed: "F",
};

interface Reading {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

export function buildSqueezeMarkers(path: SqueezePath): SeriesMarker<Time>[] {
  const currentDiscoveryDate = path.entry.firstDiscoveredOn;
  const notableStates = new Set(["confirmed", "failed", "exhausted"]);
  const confirmedPriorEpisodes = Array.from(
    new Set(
      path.stateHistory
        .filter(
          (change) =>
            !change.isCurrentEpisode &&
            change.state === "confirmed" &&
            change.episodeNumber < path.discoveryNumber,
        )
        .map((change) => change.episodeNumber),
    ),
  ).slice(-2);
  const visibleEpisodes = new Set([path.discoveryNumber, ...confirmedPriorEpisodes]);

  const markers: SeriesMarker<Time>[] = path.stateHistory
    .filter((change) => {
      const isDiscovery = change.previousState === null || change.previousState === "none";
      return (
        visibleEpisodes.has(change.episodeNumber) &&
        (isDiscovery ||
          notableStates.has(change.state) ||
          (change.isCurrentEpisode && change.state === "trigger_ready"))
      );
    })
    .map((change) => {
      const isDiscovery = change.previousState === null || change.previousState === "none";
      const late = change.state === "failed" || change.state === "exhausted";
      const markerCode = isDiscovery ? "D" : (STATE_MARKER[change.state] ?? "S");
      return {
        time: change.date as Time,
        position: late ? "aboveBar" : "belowBar",
        color: !change.isCurrentEpisode
          ? COLORS.priorEpisode
          : isDiscovery
            ? COLORS.discovery
            : change.state === "confirmed"
              ? COLORS.up
              : late
                ? COLORS.down
                : COLORS.ema20,
        shape: late ? "arrowDown" : "arrowUp",
        text: `${markerCode}${change.episodeNumber}`,
      };
    });

  // A malformed legacy episode may not have retained its first transition. The current
  // discovery still receives an explicit anchor rather than silently disappearing.
  if (!markers.some((marker) => marker.text === `D${path.discoveryNumber}`)) {
    markers.push({
      time: currentDiscoveryDate as Time,
      position: "belowBar",
      color: COLORS.discovery,
      shape: "arrowUp",
      text: `D${path.discoveryNumber}`,
    });
  }
  return markers.sort((left, right) =>
    String(left.time).localeCompare(String(right.time)),
  );
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
      // rightOffset keeps the newest candles clear of the price axis and its level labels.
      timeScale: { borderColor: border, fixLeftEdge: true, fixRightEdge: true, rightOffset: 6 },
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

    // Keep the active episode and at most two prior episodes that actually confirmed. The full
    // transition archive remains available from the date selector; rendering every historical
    // observation turned the price chart into an unreadable wall of labels.
    candles.setMarkers(buildSqueezeMarkers(path));

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

    // No `title`: lightweight-charts renders a price-line title INSIDE the pane, pinned to the
    // right edge, which buried the most recent candles under a stack of coloured chips — the
    // newest bars are the ones a reader actually needs. The price still appears on the right
    // axis (outside the plot) and the levels row below names each line with its value.
    const level = (price: number | null, color: string, style: LineStyle) => {
      if (price === null) return;
      candles.createPriceLine({
        price,
        color,
        lineWidth: 1,
        lineStyle: style,
        axisLabelVisible: true,
      });
    };
    // Only operational levels are drawn: the trigger is where the setup activates and the
    // invalidation is where it dies. The 2R objective is derived arithmetic reported in the
    // metrics — drawing it as a chart line reads as a price forecast, and it frequently sits
    // outside the autoscaled range anyway, so the line would be invisible as often as not.
    level(path.entry.discoveryPrice, COLORS.discovery, LineStyle.Dotted);
    level(path.entry.triggerPrice, COLORS.trigger, LineStyle.Dashed);
    level(path.entry.invalidationPrice, COLORS.invalidation, LineStyle.Dashed);

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

  const ordinal = (value: number) => {
    const suffix = value === 1 ? "st" : value === 2 ? "nd" : value === 3 ? "rd" : "th";
    return `${value}${suffix}`;
  };

  return (
    <div className="squeeze-chart">
      <div className="squeeze-chart__discovery">
        <span className="squeeze-chart__discovery-dot" aria-hidden="true" />
        <span>
          {path.discoveryNumber > 1 ? `${ordinal(path.discoveryNumber)} discovery` : "Discovered"}{" "}
          <strong>{path.entry.firstDiscoveredOn}</strong>
          {path.entry.discoveryPrice !== null && (
            <> at {path.entry.discoveryPrice.toFixed(2)}</>
          )}
        </span>
        {path.priorDiscoveryDates.length > 0 && (
          <em title={`Prior setups on ${path.priorDiscoveryDates.join(", ")}`}>
            {path.priorDiscoveryDates.length} earlier setup
            {path.priorDiscoveryDates.length === 1 ? "" : "s"} on record
          </em>
        )}
      </div>
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
      {/* The level names live here rather than inside the pane, where they used to sit on top
          of the most recent candles. Value included so the axis label is identifiable. */}
      <div className="squeeze-chart__levels">
        {(
          [
            ["Trigger", path.entry.triggerPrice, COLORS.trigger],
            ["Discovered", path.entry.discoveryPrice, COLORS.discovery],
            ["Invalidation", path.entry.invalidationPrice, COLORS.invalidation],
          ] as const
        )
          .filter(([, value]) => value !== null)
          .map(([label, value, color]) => (
            <span key={label}>
              <i style={{ background: color }} />
              {label} <strong>{(value as number).toFixed(2)}</strong>
            </span>
          ))}
      </div>
      <div className="squeeze-chart__legend">
        <span><i style={{ background: COLORS.ema20 }} />EMA 20</span>
        <span><i style={{ background: COLORS.ema50 }} />EMA 50</span>
        <span><i style={{ background: COLORS.vwap }} />Anchored VWAP</span>
      </div>
      <div className="squeeze-chart__marker-key" aria-label="Chart event marker legend">
        <span><b>D#</b> discovery</span>
        <span><b>T#</b> trigger</span>
        <span><b>C#</b> confirmed</span>
        <span><b>F#</b> failed</span>
        <span><b>X#</b> extended</span>
        <em>Current + 2 recent confirmed episodes</em>
      </div>
      <p className="squeeze-chart__basis">
        {path.priceBasis} {path.overlayBasis}
      </p>
    </div>
  );
}
