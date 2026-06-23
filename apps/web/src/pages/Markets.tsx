import { type FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type Screen, type ScreensResponse } from "../lib/api";
import { Spinner, taka } from "../components/ui";

// Format a screen's metric for display, based on its value_label.
function fmtValue(label: string, v: number): string {
  if (label === "RSI") return v.toFixed(0);
  if (label === "CMF") return v.toFixed(2);
  if (label.includes("avg vol")) return `${v.toFixed(1)}x`;
  if (label.includes("%")) return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
  return v.toFixed(2);
}

function ScreenCard({ s }: { s: Screen }) {
  // Only movers (today's price change) are color-coded by sign; technical metrics stay neutral
  // so nothing reads as a "buy/sell" cue.
  const isMover = s.key === "top_gainers" || s.key === "top_losers";
  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <div className="font-semibold text-sm">{s.title}</div>
      <div className="text-[11px] text-muted">{s.description}</div>
      <div className="mt-2 flex flex-col">
        {s.items.slice(0, 6).map((it) => (
          <Link
            key={it.code}
            to={`/s/${it.code}`}
            className="flex items-center justify-between py-1.5 border-t border-border/60 first:border-t-0"
          >
            <span className="font-bold text-[13px]">${it.code}</span>
            <span className="flex items-baseline gap-2">
              <span className="text-xs text-muted tnum">{taka(it.last_close)}</span>
              <span
                className={`text-xs font-semibold tnum ${
                  isMover ? (it.value >= 0 ? "text-up" : "text-down") : "text-accent"
                }`}
              >
                {fmtValue(s.value_label, it.value)}
              </span>
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}

export function Markets() {
  const [data, setData] = useState<ScreensResponse | null>(null);
  const [q, setQ] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    api
      .screens()
      .then(setData)
      .catch(() => setData({ as_of: null, screens: [] }));
  }, []);

  const search = (e: FormEvent) => {
    e.preventDefault();
    const code = q.trim().toUpperCase();
    if (code) navigate(`/s/${code}`);
  };

  if (data === null) return <Spinner />;
  const screens = data.screens.filter((s) => s.items.length > 0);

  return (
    <div className="flex flex-col gap-3">
      <form onSubmit={search}>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search a code, e.g. GP → Enter"
          className="w-full bg-surface border border-border rounded-xl px-3 py-2 text-sm outline-none focus:border-accent"
        />
      </form>

      <div className="flex items-center justify-between px-1">
        <div className="text-[11px] uppercase tracking-wide text-muted">Discover · screens</div>
        {data.as_of && <div className="text-[10px] text-muted">as of {data.as_of} close</div>}
      </div>

      {screens.map((s) => (
        <ScreenCard key={s.key} s={s} />
      ))}

      <p className="text-[10px] text-muted px-1 pb-2">
        Computed from end-of-day prices · descriptive screens, not recommendations.
      </p>
    </div>
  );
}
