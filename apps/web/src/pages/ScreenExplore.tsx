import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type Screen } from "../lib/api";
import { Spinner } from "../components/ui";
import { InfoTip } from "../components/InfoTip";
import { LESSONS, SCREEN_LESSON } from "../lib/lessons";
import { ScreenRow, SCREEN_HELP, metricHeader } from "./Markets";

const GROUP_LABEL: Record<string, string> = {
  movers: "Movers",
  community: "Community",
  value: "Value & income",
  technical: "Technical",
};
const PERIODS = [
  { id: "1d", label: "1D" },
  { id: "5d", label: "5D" },
  { id: "7d", label: "7D" },
  { id: "15d", label: "15D" },
  { id: "1m", label: "1M" },
];
const WINDOWS = [
  { id: "3m", label: "3M" },
  { id: "6m", label: "6M" },
  { id: "12m", label: "12M" },
];
// Unusual volume: spike (1D) vs sustained interest (5D / 1M).
const VOL_PERIODS = [
  { id: "1d", label: "1D" },
  { id: "5d", label: "5D" },
  { id: "1m", label: "1M" },
];

// Inline "How to read this" — the explainer lives on the page, no navigation. Default open so a
// trader sees how to use the screen the moment they land on it.
function InlineExplainer({ lessonId }: { lessonId: string }) {
  const [open, setOpen] = useState(true);
  const lesson = LESSONS[lessonId];
  if (!lesson) return null;
  const rows: { label: string; body: string }[] = [
    { label: "How traders use it", body: lesson.use },
    { label: "Watch out for", body: lesson.watch },
    { label: "Example", body: lesson.example },
  ];
  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between text-accent font-semibold text-sm"
      >
        <span>📖 How to read this</span>
        <span className="text-muted">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="mt-2 flex flex-col gap-2">
          {rows.map((r) => (
            <div key={r.label}>
              <div className="text-[11px] uppercase tracking-wide text-muted">{r.label}</div>
              <p className="text-[12px] leading-snug mt-0.5">{r.body}</p>
            </div>
          ))}
          <p className="text-[10px] text-muted">Educational only — not a recommendation.</p>
        </div>
      )}
    </div>
  );
}

// Explore page scoped to ONE category: tabs are that category's screens; the active screen shows
// its full list. Movers get a 1D/5D/1M filter; momentum gets a 3M/6M/12M filter.
export function ScreenExplore() {
  const { key = "" } = useParams();
  const [all, setAll] = useState<Screen[]>([]);
  const [active, setActive] = useState(key);
  const [period, setPeriod] = useState("1d");
  const [window, setWindow] = useState("12m");
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
  const isMomentum = active === "momentum_12_1";
  const isVolume = active === "unusual_volume";
  const usesPeriod = isMover || isVolume; // both filter by trailing-day period
  const lessonId = SCREEN_LESSON[active];

  useEffect(() => {
    if (!active) return;
    setScreen(null);
    api
      .screen(active, 50, usesPeriod ? period : undefined, isMomentum ? window : undefined)
      .then(setScreen)
      .catch(() => setScreen(null));
  }, [active, period, window, usesPeriod, isMomentum]);

  return (
    <div className="flex flex-col gap-3">
      <Link to="/markets" className="text-xs text-accent px-1">
        ← Markets
      </Link>
      {group && (
        <div className="text-[11px] uppercase tracking-wide text-muted px-1">
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

      {(isMover || isMomentum || isVolume) && (
        <div className="flex gap-2">
          {(isMomentum ? WINDOWS : isVolume ? VOL_PERIODS : PERIODS).map((p) => {
            const sel = isMomentum ? window === p.id : period === p.id;
            return (
              <button
                key={p.id}
                onClick={() => (isMomentum ? setWindow(p.id) : setPeriod(p.id))}
                className={`text-[11px] font-semibold px-2.5 py-1 rounded-full ${
                  sel ? "text-accent bg-accent/10" : "text-muted"
                }`}
              >
                {p.label}
              </button>
            );
          })}
        </div>
      )}
      {isMover && period === "1m" && (
        <p className="text-[10px] text-muted px-1 -mt-1">
          1-month moves often reverse. For a lasting trend, see “Strongest trend”.
        </p>
      )}

      {lessonId && <InlineExplainer key={lessonId} lessonId={lessonId} />}

      {screen === null ? (
        <Spinner />
      ) : (
        <div className="bg-surface border border-border rounded-2xl p-4">
          <div className="flex items-center gap-1.5">
            <div className="font-semibold text-sm text-accent">{screen.title}</div>
            <InfoTip text={SCREEN_HELP[screen.key] ?? screen.description} />
          </div>
          <div className="text-[11px] text-muted">{screen.description}</div>
          <div className="mt-2 flex justify-between text-[10px] uppercase tracking-wide text-muted/70 pb-1">
            <span className="pl-7">Symbol</span>
            <span className="flex gap-3">
              <span>Price</span>
              <span className="w-20 text-right">{metricHeader(screen.value_label)}</span>
            </span>
          </div>
          <div className="flex flex-col">
            {screen.items.map((it, i) => (
              <ScreenRow key={it.code} item={it} screen={screen} rank={i + 1} />
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
