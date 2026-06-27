import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Screen } from "../lib/api";
import { fmtValue } from "../pages/Markets";
import { taka } from "./ui";

// The day's biggest cross-factor signals at a glance — one tappable line each, pulled from the
// screens we already compute. The trader's 5-second morning read. Descriptive, not advice.
// `tag` overrides the value text when the screen's raw metric (e.g. CMF) wouldn't read plainly.
const PICKS: { key: string; icon: string; label: string; tag?: string }[] = [
  { key: "top_gainers", icon: "🚀", label: "Top mover" },
  { key: "momentum_12_1", icon: "📈", label: "Strongest trend" },
  { key: "quiet_accumulation", icon: "🧲", label: "Quiet accumulation", tag: "Accumulating" },
  { key: "beating_market", icon: "💪", label: "Beating the market" },
  { key: "foreign_buying", icon: "🌐", label: "Foreign buying" },
  { key: "unusual_volume", icon: "📊", label: "Unusual volume" },
];

export function TodayStandouts() {
  const [screens, setScreens] = useState<Screen[] | null>(null);

  useEffect(() => {
    api
      .screens()
      .then((r) => setScreens(r.screens))
      .catch(() => setScreens([]));
  }, []);

  if (!screens) return null;
  const byKey = new Map(screens.map((s) => [s.key, s]));
  const rows = PICKS.flatMap((p) => {
    const screen = byKey.get(p.key);
    const item = screen?.items[0];
    return screen && item ? [{ ...p, screen, item }] : [];
  });
  if (!rows.length) return null;

  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <div className="text-accent font-semibold text-sm">⚡ Today's standouts</div>
      <div className="text-[11px] text-muted">
        The day's biggest signals at a glance — descriptive, not advice.
      </div>
      <div className="mt-2 flex flex-col">
        {rows.map((r) => (
          <Link
            key={r.key}
            to={`/s/${r.item.code}`}
            className="flex items-center justify-between gap-2 py-2 border-t border-border/60 first:border-t-0"
          >
            <span className="flex items-center gap-2 min-w-0">
              <span className="shrink-0 text-base">{r.icon}</span>
              <span className="flex flex-col min-w-0">
                <span className="text-[11px] text-muted leading-tight">{r.label}</span>
                <span className="font-bold text-[13px]">${r.item.code}</span>
              </span>
            </span>
            <span className="flex items-baseline gap-2 shrink-0">
              <span className="text-xs text-muted tnum">{taka(r.item.last_close)}</span>
              <span className="text-xs font-semibold text-accent tnum">
                {r.tag ?? r.item.note ?? fmtValue(r.screen.value_label, r.item.value)}
              </span>
            </span>
          </Link>
        ))}
      </div>
      <Link to="/markets" className="block text-center text-[11px] text-accent mt-2 pt-2 border-t border-border/60">
        Explore all screens →
      </Link>
    </div>
  );
}
