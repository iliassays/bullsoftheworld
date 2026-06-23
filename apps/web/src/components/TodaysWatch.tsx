import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type TodaysWatch as TodaysWatchT } from "../lib/api";

// AI "Today's Watch" — a grounded daily highlight + clickable movers/chatter chips.
export function TodaysWatch() {
  const [data, setData] = useState<TodaysWatchT | null>(null);

  useEffect(() => {
    api.todaysWatch().then(setData).catch(() => {});
  }, []);

  if (!data || (!data.summary && data.items.length === 0)) return null;

  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <div className="text-accent font-semibold text-sm">📋 Today's Watch</div>
      {data.summary && (
        <p className="text-[15px] leading-relaxed mt-2 text-text/90">{data.summary}</p>
      )}
      <div className="flex gap-1.5 flex-wrap mt-3">
        {data.items.slice(0, 8).map((it) => (
          <Link
            key={it.code}
            to={`/s/${it.code}`}
            className="text-xs bg-card border border-border rounded-full px-2.5 py-1"
          >
            ${it.code}{" "}
            <span className={`tnum ${it.change_pct >= 0 ? "text-up" : "text-down"}`}>
              {it.change_pct >= 0 ? "+" : ""}
              {it.change_pct.toFixed(1)}%
            </span>
            {it.posts > 0 && <span className="text-muted"> · {it.posts}💬</span>}
          </Link>
        ))}
      </div>
      <p className="text-[10px] text-muted mt-2">
        AI-generated from today's moves + chatter. Not financial advice.
      </p>
    </div>
  );
}
