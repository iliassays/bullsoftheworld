import type { DossierPricePoint } from "./model";

const WIDTH = 840;
const HEIGHT = 250;
const PRICE_TOP = 18;
const PRICE_BOTTOM = 172;
const VOLUME_TOP = 195;
const VOLUME_BOTTOM = 232;

function coordinate(value: number, minimum: number, maximum: number): number {
  if (maximum === minimum) return (PRICE_TOP + PRICE_BOTTOM) / 2;
  return PRICE_BOTTOM - ((value - minimum) / (maximum - minimum)) * (PRICE_BOTTOM - PRICE_TOP);
}

export function DossierChart({ points }: { points: readonly DossierPricePoint[] }) {
  if (points.length < 2) {
    return <div className="dossier-chart--empty">Price history is not available at this cutoff.</div>;
  }
  const closes = points.map((point) => point.close);
  const minimum = Math.min(...closes);
  const maximum = Math.max(...closes);
  const maxVolume = Math.max(...points.map((point) => point.volume), 1);
  const first = points[0]!;
  const last = points[points.length - 1]!;
  const step = WIDTH / Math.max(points.length - 1, 1);
  const polyline = points
    .map((point, index) => `${index * step},${coordinate(point.close, minimum, maximum)}`)
    .join(" ");
  const positive = last.close >= first.close;
  const barWidth = Math.max(1, Math.min(5, (WIDTH / points.length) * 0.7));

  return (
    <div className="dossier-chart">
      <svg
        aria-label={`${points.length}-session adjusted closing-price and volume chart`}
        preserveAspectRatio="none"
        role="img"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      >
        {[0, 0.5, 1].map((fraction) => {
          const y = PRICE_TOP + fraction * (PRICE_BOTTOM - PRICE_TOP);
          return <line className="dossier-chart__grid" key={fraction} x1="0" x2={WIDTH} y1={y} y2={y} />;
        })}
        {points.map((point, index) => {
          const height = (point.volume / maxVolume) * (VOLUME_BOTTOM - VOLUME_TOP);
          return (
            <rect
              className="dossier-chart__volume"
              height={height}
              key={point.date}
              width={barWidth}
              x={index * step - barWidth / 2}
              y={VOLUME_BOTTOM - height}
            />
          );
        })}
        <polyline
          className={positive ? "dossier-chart__line dossier-chart__line--up" : "dossier-chart__line dossier-chart__line--down"}
          fill="none"
          points={polyline}
          vectorEffect="non-scaling-stroke"
        />
      </svg>
      <span className="dossier-chart__high tnum">{maximum.toFixed(2)}</span>
      <span className="dossier-chart__low tnum">{minimum.toFixed(2)}</span>
      <span className="dossier-chart__from">{first.date}</span>
      <span className="dossier-chart__to">{last.date}</span>
    </div>
  );
}
