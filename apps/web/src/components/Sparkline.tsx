// A tiny inline price-trend line — see the shape (climbing / spiking / recovering) at a glance.
// Coloured by net direction over the window (last vs first close). Purely descriptive.
export function Sparkline({
  data,
  width = 56,
  height = 18,
}: {
  data: number[];
  width?: number;
  height?: number;
}) {
  if (!data || data.length < 2) return <span style={{ width, height }} className="inline-block" />;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const dx = width / (data.length - 1);
  const pts = data
    .map((v, i) => `${(i * dx).toFixed(1)},${(height - ((v - min) / span) * height).toFixed(1)}`)
    .join(" ");
  const up = data[data.length - 1] >= data[0];
  const color = up ? "var(--color-up, #16c784)" : "var(--color-down, #ea3943)";
  return (
    <svg width={width} height={height} className="shrink-0" aria-hidden>
      <polyline
        points={pts}
        fill="none"
        stroke={color}
        strokeWidth={1.25}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}
