import { useId } from "react";

// A tiny inline price-trend line — see the shape (climbing / spiking / recovering) at a glance.
// Coloured by net direction over the window (last vs first close). Purely descriptive.
// A faint area fill under the line and a dot on the endpoint give the eye a trend to land on
// without having to read the line in isolation against a bare background.
export function Sparkline({
  data,
  width = 56,
  height = 18,
}: {
  data: number[];
  width?: number;
  height?: number;
}) {
  const gradientId = useId();
  if (!data || data.length < 2) return <span style={{ width, height }} className="inline-block" />;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const dx = width / (data.length - 1);
  const coords = data.map((v, i) => [
    i * dx,
    height - ((v - min) / span) * height,
  ]);
  const pts = coords.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const [lastX, lastY] = coords[coords.length - 1];
  const areaPts = `0,${height} ${pts} ${lastX.toFixed(1)},${height}`;
  const up = data[data.length - 1] >= data[0];
  const color = up ? "var(--color-up, #2fbf71)" : "var(--color-down, #f0564a)";
  return (
    <svg width={width} height={height} className="shrink-0" aria-hidden>
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.28} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>
      <polyline points={areaPts} fill={`url(#${gradientId})`} stroke="none" />
      <polyline
        points={pts}
        fill="none"
        stroke={color}
        strokeWidth={1.25}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle cx={lastX} cy={lastY} r={1.8} fill={color} />
    </svg>
  );
}
