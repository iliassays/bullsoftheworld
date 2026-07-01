import { useRef, useState } from "react";

// Dependency-free stacked bar chart (SVG) with an interactive hover tooltip + crosshair.
// Full-width, fixed height; up to N daily points, one or two stacked series.

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

  const wrapRef = useRef<HTMLDivElement>(null);
  const [hi, setHi] = useState<number | null>(null);

  function onMove(e: React.MouseEvent) {
    const r = wrapRef.current?.getBoundingClientRect();
    if (!r) return;
    const i = Math.floor(((e.clientX - r.left) / r.width) * n);
    setHi(Math.min(n - 1, Math.max(0, i)));
  }

  const hp = hi != null ? points[hi] : null;
  const leftPct = hi != null ? ((hi + 0.5) / n) * 100 : 0;
  const clampedLeft = Math.min(88, Math.max(12, leftPct)); // keep the tooltip in bounds

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

      <div
        ref={wrapRef}
        className="relative"
        style={{ height, cursor: "crosshair" }}
        onMouseMove={onMove}
        onMouseLeave={() => setHi(null)}
      >
        <svg
          viewBox={`0 0 ${W} ${height}`}
          preserveAspectRatio="none"
          width="100%"
          height={height}
          style={{ display: "block" }}
        >
          {/* hovered-column highlight */}
          {hi != null && (
            <rect x={hi * slot} y={0} width={slot} height={height} fill="var(--color-text)" opacity={0.06} />
          )}
          {points.map((p, i) => {
            let cum = 0;
            const x = i * slot + pad;
            return (
              <g key={p.date}>
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

        {/* tooltip */}
        {hp && (
          <div
            className="pointer-events-none absolute z-10 rounded-lg border border-border bg-surface px-2.5 py-1.5 shadow-lg"
            style={{ left: `${clampedLeft}%`, top: 2, transform: "translateX(-50%)", minWidth: 110 }}
          >
            <div className="text-[11px] font-semibold text-text mb-0.5">{hp.date}</div>
            {series.map((s) => (
              <div key={s.key} className="flex items-center gap-1.5 text-[11px] text-muted">
                <span className="inline-block w-2 h-2 rounded-sm" style={{ background: s.color }} />
                <span className="text-text tnum">{val(hp, s.key)}</span>
                <span>{s.label}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="flex justify-between text-[10px] text-muted mt-1">
        <span>{points[0]?.date.slice(5)}</span>
        <span>{points[Math.floor(n / 2)]?.date.slice(5)}</span>
        <span>{points[n - 1]?.date.slice(5)}</span>
      </div>
    </div>
  );
}
