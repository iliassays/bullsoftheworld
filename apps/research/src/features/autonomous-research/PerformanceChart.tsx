interface ChartPoint {
  date: string;
  nav: number;
  benchmark: number;
}

function path(values: number[], width: number, height: number, minimum: number, maximum: number) {
  const range = Math.max(maximum - minimum, 1);
  return values
    .map((value, index) => {
      const x = values.length === 1 ? 0 : (index / (values.length - 1)) * width;
      const y = height - ((value - minimum) / range) * height;
      return `${index ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
}

export function PerformanceChart({ points }: { points: ChartPoint[] }) {
  if (points.length < 2) return <div className="atlas-chart atlas-chart--empty">Awaiting enough completed sessions.</div>;
  const width = 900;
  const height = 220;
  const values = points.flatMap((point) => [point.nav, point.benchmark]);
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  return (
    <div className="atlas-chart">
      <svg aria-label="Portfolio and benchmark net asset value" preserveAspectRatio="none" role="img" viewBox={`0 0 ${width} ${height}`}>
        {[0, 0.25, 0.5, 0.75, 1].map((fraction) => (
          <line className="atlas-chart__grid" key={fraction} x1="0" x2={width} y1={height * fraction} y2={height * fraction} />
        ))}
        <path className="atlas-chart__benchmark" d={path(points.map((point) => point.benchmark), width, height, minimum, maximum)} fill="none" />
        <path className="atlas-chart__portfolio" d={path(points.map((point) => point.nav), width, height, minimum, maximum)} fill="none" />
      </svg>
      <span className="atlas-chart__range"><small>{points[0]!.date}</small><small>{points[points.length - 1]?.date}</small></span>
      <span className="atlas-chart__legend"><i /> Portfolio <i /> Observable-universe benchmark</span>
    </div>
  );
}
