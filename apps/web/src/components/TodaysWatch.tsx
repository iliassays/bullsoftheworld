import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Breadth, type TodaysWatch as TodaysWatchT } from "../lib/api";

// The DSE day, in Dhaka time, picks the heading — Morning / Midday / Evening / Weekend.
function dhakaSession(): { label: string; icon: string } {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-US", {
      timeZone: "Asia/Dhaka",
      weekday: "short",
      hour: "2-digit",
      hour12: false,
    })
      .formatToParts(new Date())
      .map((p) => [p.type, p.value]),
  );
  const weekday = parts.weekday;
  const hour = parseInt(parts.hour, 10);
  if (weekday === "Fri" || weekday === "Sat") return { label: "Weekend Review", icon: "📅" };
  if (hour < 10) return { label: "Morning Brief", icon: "🌅" };
  if (hour < 15) return { label: "Midday Pulse", icon: "☀️" };
  return { label: "Evening Wrap", icon: "🌙" };
}

function BreadthBar({ b }: { b: Breadth }) {
  const traded = b.advancers + b.decliners + b.unchanged || 1;
  const up = (b.advancers / traded) * 100;
  const flat = (b.unchanged / traded) * 100;
  return (
    <div className="mt-3">
      <div className="flex justify-between text-[11px] mb-1">
        <span className="text-up tnum">▲ {b.advancers}</span>
        <span className="text-muted tnum">{b.unchanged} flat</span>
        <span className="text-down tnum">{b.decliners} ▼</span>
      </div>
      <div className="flex h-1.5 rounded-full overflow-hidden bg-card">
        <div className="bg-up" style={{ width: `${up}%` }} />
        <div className="bg-muted/40" style={{ width: `${flat}%` }} />
        <div className="bg-down flex-1" />
      </div>
    </div>
  );
}

// AI daily brief — session-aware heading + market breadth + clickable movers/chatter chips.
export function TodaysWatch() {
  const [data, setData] = useState<TodaysWatchT | null>(null);
  const session = dhakaSession();

  useEffect(() => {
    api.todaysWatch().then(setData).catch(() => {});
  }, []);

  if (!data || (!data.summary && data.items.length === 0)) return null;

  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <div className="text-accent font-semibold text-sm">
        {session.icon} {session.label}
      </div>
      {data.breadth && data.breadth.total > 0 && <BreadthBar b={data.breadth} />}
      {data.summary && (
        <p className="text-[15px] leading-relaxed mt-3 text-text/90">{data.summary}</p>
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
