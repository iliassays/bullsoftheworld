// Dependency-free stacked bar chart (SVG). Full-width, fixed height; up to N daily points,
// one or two stacked series. No external chart lib — keeps the bundle tiny and CSP-safe.

export interface Series {
  key: string;
  color: string; // CSS color (use theme vars)
  label: string;
}

type Point = { date: string };
const val = (p: Point, key: string) => Number((p as Record<string, unknown>)[key]) || 0;

export function Bars({
  points,
  series,
  height = 150,
}: {
  points: Point[];
  series: Series[];
  height?: number;
}) {
  const n = Math.max(points.length, 1);
  const W = 1000;
  const slot = W / n;
  const barW = slot * 0.72;
  const pad = (slot - barW) / 2;
  const total = (p: Point) => series.reduce((s, se) => s + val(p, se.key), 0);
  const max = Math.max(1, ...points.map(total));

  return (
    <div>
      <div className="flex items-center gap-3 mb-2 text-[11px] text-muted">
        {series.map((s) => (
          <span key={s.key} className="flex items-center gap-1">
            <span className="inline-block w-2.5 h-2.5 rounded-sm" style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
        <span className="ml-auto">peak {max}/day</span>
      </div>
      <svg
        viewBox={`0 0 ${W} ${height}`}
        preserveAspectRatio="none"
        width="100%"
        height={height}
        style={{ display: "block" }}
      >
        {points.map((p, i) => {
          let cum = 0;
          const x = i * slot + pad;
          return (
            <g key={p.date}>
              <title>
                {p.date} — {series.map((s) => `${s.label}: ${val(p, s.key)}`).join(", ")}
              </title>
              {/* faint baseline slot so empty days are still visible */}
              <rect x={x} y={height - 1} width={barW} height={1} fill="var(--color-border)" />
              {series.map((s) => {
                const v = val(p, s.key);
                if (!v) return null;
                const h = (v / max) * (height - 2);
                const y = height - h - cum;
                cum += h;
                return <rect key={s.key} x={x} y={y} width={barW} height={h} fill={s.color} rx={1} />;
              })}
            </g>
          );
        })}
      </svg>
      <div className="flex justify-between text-[10px] text-muted mt-1">
        <span>{points[0]?.date.slice(5)}</span>
        <span>{points[Math.floor(n / 2)]?.date.slice(5)}</span>
        <span>{points[n - 1]?.date.slice(5)}</span>
      </div>
      {/* one-line takeaway */}
      <div className="sr-only">
        {points.reduce((s, p) => s + total(p), 0)} total over {n} days
      </div>
    </div>
  );
}
