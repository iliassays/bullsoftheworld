import { useEffect, useRef, useState } from "react";
import {
  ColorType,
  CrosshairMode,
  LineStyle,
  type SeriesMarker,
  type Time,
  createChart,
} from "lightweight-charts";

import type { DecisionCandidatePath, DecisionEvent } from "../../app/api-client";

interface DecisionPathChartProps {
  path: DecisionCandidatePath;
}

function marker(event: DecisionEvent): SeriesMarker<Time> | null {
  const time = event.effectiveDate as Time;
  if (event.eventType === "signal" || event.eventType === "target") {
    const action = String(event.payload.action ?? event.payload.qualification ?? "signal");
    const exit = action.includes("exit") || action.includes("reduce");
    return {
      time,
      position: exit ? "aboveBar" : "belowBar",
      color: exit ? "#bd3e43" : "#a76b00",
      shape: exit ? "arrowDown" : "arrowUp",
      text: exit ? "Exit target" : "Discovered",
    };
  }
  if (event.eventType === "fill") {
    const sell = event.payload.side === "sell";
    return {
      time,
      position: sell ? "aboveBar" : "belowBar",
      color: sell ? "#bd3e43" : "#14835f",
      shape: sell ? "arrowDown" : "arrowUp",
      text: sell ? "Sell fill" : "Buy fill",
    };
  }
  if (event.eventType === "risk" || event.eventType === "rejection") {
    return {
      time,
      position: "aboveBar",
      color: "#bd3e43",
      shape: "circle",
      text: event.eventType === "rejection" ? "Blocked" : "Risk",
    };
  }
  return null;
}

export function DecisionPathChart({ path }: DecisionPathChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<{ date: string; close: number } | null>(null);

  useEffect(() => {
    const element = containerRef.current;
    if (!element || path.points.length < 2) return;
    const styles = getComputedStyle(element);
    const text = styles.getPropertyValue("--text-muted").trim() || "#68717b";
    const border = styles.getPropertyValue("--border").trim() || "#e4e6e1";
    const chart = createChart(element, {
      autoSize: true,
      height: 340,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: text,
        attributionLogo: false,
        fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
        fontSize: 10,
      },
      grid: {
        vertLines: { color: border },
        horzLines: { color: border },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: {
        borderColor: border,
        scaleMargins: { top: 0.08, bottom: 0.27 },
      },
      timeScale: {
        borderColor: border,
        fixLeftEdge: true,
        fixRightEdge: true,
        rightOffset: 3,
      },
      localization: { priceFormatter: (price: number) => price.toFixed(2) },
    });
    const price = chart.addLineSeries({
      color: "#a76b00",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
    });
    price.setData(path.points.map((point) => ({
      time: point.date as Time,
      value: point.close,
    })));
    const available = new Set(path.points.map((point) => point.date));
    price.setMarkers(
      path.events
        .filter((event) => available.has(event.effectiveDate))
        .flatMap((event) => {
          const value = marker(event);
          return value ? [value] : [];
        })
        .sort((left, right) => String(left.time).localeCompare(String(right.time))),
    );
    if (path.candidate.discoveryPrice !== null) {
      price.createPriceLine({
        price: path.candidate.discoveryPrice,
        color: "#68717b",
        lineStyle: LineStyle.Dashed,
        lineWidth: 1,
        axisLabelVisible: true,
        title: "First discovery",
      });
    }
    const volume = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    volume.priceScale().applyOptions({ scaleMargins: { top: 0.78, bottom: 0 } });
    volume.setData(path.points.map((point, index) => ({
      time: point.date as Time,
      value: point.volume,
      color: index > 0 && point.close < path.points[index - 1]!.close
        ? "rgba(189, 62, 67, 0.28)"
        : "rgba(20, 131, 95, 0.28)",
    })));
    chart.subscribeCrosshairMove((parameter) => {
      if (!parameter.time) {
        setHover(null);
        return;
      }
      const reading = parameter.seriesData.get(price);
      if (!reading || !("value" in reading)) return;
      setHover({ date: String(parameter.time), close: reading.value });
    });
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [path]);

  const latest = path.points.at(-1);
  const reading = hover ?? (latest ? { date: latest.date, close: latest.close } : null);

  return (
    <div className="decision-path-chart">
      <div className="decision-path-chart__reading" aria-live="polite">
        <span>{reading?.date ?? "No completed prices"}</span>
        <strong>{reading?.close.toFixed(2) ?? "—"}</strong>
      </div>
      <div aria-label={`${path.candidate.code} adjusted price since discovery`} ref={containerRef} />
    </div>
  );
}
