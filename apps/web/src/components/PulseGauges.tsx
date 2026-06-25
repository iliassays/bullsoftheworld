import { useEffect, useState } from "react";
import { api, type Pulse } from "../lib/api";

// Pulse — three descriptive dials from community activity. Counts only, no advice.
export function PulseGauges({ code }: { code: string }) {
  const [pulse, setPulse] = useState<Pulse | null>(null);

  useEffect(() => {
    setPulse(null);
    api
      .pulse(code)
      .then(setPulse)
      .catch(() => setPulse(null));
  }, [code]);

  if (!pulse) return null;

  const sentColor =
    pulse.sentiment.score >= 55
      ? "bg-up"
      : pulse.sentiment.score <= 45
        ? "bg-down"
        : "bg-muted";

  const row = (
    title: string,
    g: { score: number; label: string },
    barCls: string,
  ) => (
    <div className="py-2">
      <div className="flex items-baseline justify-between text-xs">
        <span className="text-muted">{title}</span>
        <span className="font-semibold capitalize">
          {g.label} <span className="text-muted tnum">· {g.score}</span>
        </span>
      </div>
      <div className="mt-1 h-1.5 rounded-full bg-border overflow-hidden">
        <div className={`h-full ${barCls}`} style={{ width: `${g.score}%` }} />
      </div>
    </div>
  );

  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <div className="text-accent font-semibold text-sm">📊 Pulse</div>
      <p className="text-[10px] text-muted mb-1">
        Community activity over the last 7 days.
      </p>
      {row("Sentiment", pulse.sentiment, sentColor)}
      {row("Message volume", pulse.message_volume, "bg-accent")}
      {row("Participation", pulse.participation, "bg-accent")}
    </div>
  );
}
