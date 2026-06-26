import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type Screen } from "../lib/api";
import { Spinner, taka } from "../components/ui";
import { fmtValue } from "./Markets";

const GROUP_LABEL: Record<string, string> = {
  movers: "Movers",
  community: "Community",
  value: "Value & income",
  technical: "Technical",
};
const PERIODS = [
  { id: "1d", label: "1D" },
  { id: "5d", label: "5D" },
  { id: "1m", label: "1M" },
];

// Explore page scoped to ONE category: tabs are that category's screens; the active screen shows
// its full list. Movers also get a 1D/5D/1M timeframe filter.
export function ScreenExplore() {
  const { key = "" } = useParams();
  const [all, setAll] = useState<Screen[]>([]);
  const [active, setActive] = useState(key);
  const [period, setPeriod] = useState("1d");
  const [screen, setScreen] = useState<Screen | null>(null);

  useEffect(() => {
    api
      .screens()
      .then((r) => setAll(r.screens))
      .catch(() => setAll([]));
  }, []);
  useEffect(() => setActive(key), [key]);

  const group = all.find((s) => s.key === active)?.group;
  const tabs = all.filter((s) => s.group === group && s.items.length > 0);
  const isMover = active === "top_gainers" || active === "top_losers";

  useEffect(() => {
    if (!active) return;
    setScreen(null);
    api
      .screen(active, 50, isMover ? period : undefined)
      .then(setScreen)
      .catch(() => setScreen(null));
  }, [active, period, isMover]);

  return (
    <div className="flex flex-col gap-3">
      <Link to="/markets" className="text-xs text-accent px-1">
        ← Markets
      </Link>
      {group && (
        <div className="text-[11px] uppercase tracking-wide text-accent px-1">
          {GROUP_LABEL[group] ?? group}
        </div>
      )}

      <div className="flex gap-2 overflow-x-auto pb-1">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setActive(t.key)}
            className={`whitespace-nowrap text-xs font-semibold px-3 py-1.5 rounded-full border ${
              active === t.key ? "text-accent border-accent bg-accent/10" : "text-muted border-border"
            }`}
          >
            {t.title}
          </button>
        ))}
      </div>

      {isMover && (
        <div className="flex gap-2">
          {PERIODS.map((p) => (
            <button
              key={p.id}
              onClick={() => setPeriod(p.id)}
              className={`text-[11px] font-semibold px-2.5 py-1 rounded-full ${
                period === p.id ? "text-accent bg-accent/10" : "text-muted"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      )}

      {screen === null ? (
        <Spinner />
      ) : (
        <div className="bg-surface border border-border rounded-2xl p-4">
          <div className="font-semibold text-sm">{screen.title}</div>
          <div className="text-[11px] text-muted">{screen.description}</div>
          <div className="mt-2 flex flex-col">
            {screen.items.map((it, i) => (
              <Link
                key={it.code}
                to={`/s/${it.code}`}
                className="flex items-center justify-between py-2 border-t border-border/60 first:border-t-0"
              >
                <span className="flex items-center gap-2">
                  <span className="text-[11px] text-muted tnum w-5">{i + 1}</span>
                  <span className="font-bold text-[13px]">${it.code}</span>
                </span>
                <span className="flex items-baseline gap-2">
                  <span className="text-xs text-muted tnum">{taka(it.last_close)}</span>
                  <span
                    className={`text-xs font-semibold tnum ${
                      isMover ? (it.value >= 0 ? "text-up" : "text-down") : "text-accent"
                    }`}
                  >
                    {fmtValue(screen.value_label, it.value)}
                  </span>
                </span>
              </Link>
            ))}
            {screen.items.length === 0 && (
              <div className="text-muted text-sm py-2">Nothing here right now.</div>
            )}
          </div>
          <p className="text-[10px] text-muted mt-2">Descriptive screen — not a recommendation.</p>
        </div>
      )}
    </div>
  );
}
