import { useEffect, useRef, useState } from "react";
import { ColorType, createChart } from "lightweight-charts";
import { api } from "../lib/api";

// Daily candlestick chart for a symbol, themed to the Bull Gold dark palette.
export function CandleChart({ code }: { code: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [empty, setEmpty] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const chart = createChart(el, {
      autoSize: true,
      height: 280,
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
    const series = chart.addCandlestickSeries({
      upColor: "#16c784",
      downColor: "#ea3943",
      borderVisible: false,
      wickUpColor: "#16c784",
      wickDownColor: "#ea3943",
    });

    let alive = true;
    api
      .bars(code, 180)
      .then((bars) => {
        if (!alive) return;
        if (!bars.length) return setEmpty(true);
        series.setData(
          bars.map((b) => ({
            time: b.date,
            open: b.open,
            high: b.high,
            low: b.low,
            close: b.close,
          })),
        );
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
  return <div ref={ref} className="w-full rounded-2xl border border-border bg-surface p-2" />;
}
