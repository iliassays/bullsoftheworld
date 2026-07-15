export function Sparkline({ values, positive }: { values: readonly number[]; positive: boolean }) {
  const width = 92;
  const height = 30;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const points = values
    .map((value, index) => {
      const x = (index / Math.max(values.length - 1, 1)) * width;
      const y = height - ((value - min) / range) * (height - 4) - 2;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <svg
      aria-label={`Recent price trend ${positive ? "higher" : "lower"}`}
      className={`queue-sparkline ${positive ? "queue-sparkline--up" : "queue-sparkline--down"}`}
      role="img"
      viewBox={`0 0 ${width} ${height}`}
    >
      <polyline fill="none" points={points} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
    </svg>
  );
}
