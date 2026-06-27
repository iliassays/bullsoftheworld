import { type FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type Screen, type ScreenItem, type ScreensResponse } from "../lib/api";
import { Spinner, taka } from "../components/ui";
import { InfoTip } from "../components/InfoTip";

// Plain-language explanation per screen, with a worked example — descriptive, never advice.
export const SCREEN_HELP: Record<string, string> = {
  top_gainers:
    "Biggest price moves up over the chosen period. e.g. +7.2% means the price is 7.2% higher than where it started.",
  top_losers:
    "Biggest price moves down over the chosen period. e.g. -7.2% means the price is 7.2% lower than where it started.",
  near_support:
    "Price sitting just above a support level — a floor buyers have defended before. 'Near' = within 3% above it. e.g. $GP 2% above ৳280 support.",
  near_resistance:
    "Price approaching a resistance level — a ceiling sellers have defended before. 'Near' = within 3% below it.",
  oversold:
    "RSI rates recent momentum from 0–100. Below 30 is historically an 'oversold' zone. e.g. RSI 25. A fact about momentum, not a buy signal.",
  overbought:
    "RSI rates recent momentum from 0–100. Above 70 is historically an 'overbought' zone. e.g. RSI 78. A fact about momentum, not a sell signal.",
  accumulation:
    "Chaikin Money Flow (CMF) gauges buying vs selling pressure over 20 days, on a -1 to +1 scale. Positive = money flowing in. e.g. +0.30 = strong inflow.",
  distribution:
    "Chaikin Money Flow (CMF) below 0 means money is flowing out — net selling pressure over 20 days. e.g. -0.30 = strong outflow.",
  unusual_volume:
    "Today's traded volume vs its own 20-day average. 'Very heavy' = 3x+ normal. e.g. $WMSHIPYARD at 4.6x traded 4.6 times its usual daily volume.",
  uptrend:
    "Trading above its 200-day average price — a common longer-term uptrend marker. The % shows how far above the average it is.",
  near_52w_high: "Within 5% of its highest price over the past 52 weeks (one year).",
  near_52w_low: "Within 5% of its lowest price over the past 52 weeks (one year).",
  dividend_yield:
    "Last year's cash dividend as a % of today's price. e.g. ৳1 cash on a ৳20 price = 5%. Bonus (stock) dividends aren't counted, and price-collapse 'traps' above 15% are hidden.",
  value_vs_sector:
    "P/E compared with the sector's median. Below 1.0× = cheaper than typical peers. e.g. 0.7× means a 30% lower P/E than the sector median.",
  eps_growth: "Earnings per share vs the prior year. e.g. +20% YoY = earnings grew 20%.",
  most_watched: "The names most people have added to their watchlist.",
  most_discussed: "The names with the most community posts over the last 2 days.",
  attention_rising:
    "Discussion running well above this symbol's own usual pace. e.g. 3× usual = three times its normal daily chatter.",
  smart_money_buying:
    "Institutions and foreign investors raised their combined stake at the latest monthly disclosure. e.g. +5 pp means 'big money' ownership went up 5 percentage points. They have more to analyse with — but it's history, not a forecast.",
  most_active:
    "Most heavily traded by money value today (price × volume), shown in crore (1 Cr = ৳10 million). The classic 'top turnover' board — where the day's action is, including the cheap, busy names.",
};

// Format a screen's metric for display, based on its value_label.
export function fmtValue(label: string, v: number): string {
  if (label === "RSI") return v.toFixed(0);
  if (label === "CMF") return v.toFixed(2);
  if (label === "yield") return `${v.toFixed(1)}%`;
  if (label.includes("sector")) return `${v.toFixed(2)}×`;
  if (label.includes("avg vol") || label.includes("usual"))
    return `${v.toFixed(1)}x`;
  if (label === "watchers" || label === "posts") return v.toFixed(0);
  if (label === "turnover")
    return `৳${v.toLocaleString(undefined, { maximumFractionDigits: v >= 10 ? 0 : 1 })} Cr`;
  if (label === "pp") return `${v >= 0 ? "+" : ""}${v.toFixed(1)} pp`;
  if (label.includes("%")) return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
  return v.toFixed(2);
}

// A short, plain-language reading of the screen's jargon metric — descriptive facts only, never a
// cue to act. Returns null for metrics that are already self-explanatory (raw % / counts).
interface Chip {
  word: string;
  tone: "up" | "down" | "neutral";
}
export function metricChip(label: string, v: number): Chip | null {
  if (label === "CMF") {
    if (v >= 0.25) return { word: "Strong inflow", tone: "up" };
    if (v >= 0.05) return { word: "Inflow", tone: "up" };
    if (v <= -0.25) return { word: "Strong outflow", tone: "down" };
    if (v <= -0.05) return { word: "Outflow", tone: "down" };
    return { word: "Flat flow", tone: "neutral" };
  }
  if (label === "RSI") {
    if (v >= 70) return { word: "Overbought zone", tone: "neutral" };
    if (v <= 30) return { word: "Oversold zone", tone: "neutral" };
    if (v >= 55) return { word: "Strong momentum", tone: "neutral" };
    if (v <= 45) return { word: "Weak momentum", tone: "neutral" };
    return { word: "Neutral", tone: "neutral" };
  }
  if (label.includes("avg vol") || label.includes("usual")) {
    if (v >= 3) return { word: "Very heavy", tone: "neutral" };
    if (v >= 2) return { word: "Heavy volume", tone: "neutral" };
    return { word: "Active", tone: "neutral" };
  }
  if (label === "yield") return { word: v >= 8 ? "High yield" : "Pays dividend", tone: "neutral" };
  if (label.includes("sector")) return { word: "Cheaper than peers", tone: "neutral" };
  if (label === "% YoY") return { word: v >= 50 ? "Fast growth" : "Growing", tone: "up" };
  if (label === "pp") return { word: v >= 3 ? "Accumulating" : "Buying", tone: "up" };
  return null;
}

// Plain header for the rightmost (metric) column.
export function metricHeader(label: string): string {
  if (label === "CMF") return "Money flow";
  if (label === "RSI") return "Momentum";
  if (label.includes("avg vol") || label.includes("usual")) return "Volume";
  if (label === "yield") return "Yield";
  if (label.includes("sector")) return "vs sector";
  if (label === "% YoY") return "EPS growth";
  if (label === "watchers") return "Watchers";
  if (label === "posts") return "Posts";
  if (label === "turnover") return "Turnover";
  if (label === "pp") return "Big money";
  if (label.includes("%")) return "Change";
  return label;
}

const toneCls = (t: Chip["tone"]) =>
  t === "up" ? "text-up" : t === "down" ? "text-down" : "text-fg";

// One row, shared by the Markets cards and the explore page so they read identically.
export function ScreenRow({
  item,
  screen,
  rank,
}: {
  item: ScreenItem;
  screen: Screen;
  rank?: number;
}) {
  const isMover = screen.key === "top_gainers" || screen.key === "top_losers";
  const chip = isMover ? null : metricChip(screen.value_label, item.value);
  const showName = item.name && item.name !== item.code;
  return (
    <Link
      to={`/s/${item.code}`}
      className="flex items-center justify-between gap-2 py-2 border-t border-border/60 first:border-t-0"
    >
      <span className="flex items-center gap-2 min-w-0">
        {rank != null && (
          <span className="text-[11px] text-muted tnum w-5 shrink-0">{rank}</span>
        )}
        <span className="flex flex-col min-w-0">
          <span className="font-bold text-[13px]">${item.code}</span>
          {showName && <span className="text-[11px] text-muted truncate">{item.name}</span>}
        </span>
      </span>
      <span className="flex items-stretch gap-3 shrink-0 text-right">
        <span className="flex flex-col items-end justify-center">
          <span className="text-xs text-muted tnum">{taka(item.last_close)}</span>
          {item.change_1d != null && (
            <span
              className={`text-[11px] tnum ${item.change_1d >= 0 ? "text-up" : "text-down"}`}
            >
              {item.change_1d >= 0 ? "+" : ""}
              {item.change_1d.toFixed(1)}%
            </span>
          )}
        </span>
        <span className="flex flex-col items-end justify-center w-20">
          {isMover ? (
            <span
              className={`text-xs font-semibold tnum ${item.value >= 0 ? "text-up" : "text-down"}`}
            >
              {fmtValue(screen.value_label, item.value)}
            </span>
          ) : chip ? (
            <>
              <span className={`text-xs font-semibold ${toneCls(chip.tone)}`}>{chip.word}</span>
              <span className="text-[10px] text-muted tnum">
                {fmtValue(screen.value_label, item.value)}
              </span>
            </>
          ) : (
            <span className="text-xs font-semibold text-accent tnum">
              {fmtValue(screen.value_label, item.value)}
            </span>
          )}
        </span>
      </span>
    </Link>
  );
}

// Display order + labels. "technical" is collapsed by default (advanced).
const GROUPS: { id: string; label: string; advanced?: boolean }[] = [
  { id: "movers", label: "Movers" },
  { id: "community", label: "Community" },
  { id: "value", label: "Value & income" },
  { id: "technical", label: "Technical", advanced: true },
];

function ScreenCard({ s }: { s: Screen }) {
  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <div className="flex items-center gap-1.5">
        <div className="font-semibold text-sm text-accent">{s.title}</div>
        <InfoTip text={SCREEN_HELP[s.key] ?? s.description} />
      </div>
      <div className="text-[11px] text-muted">{s.description}</div>
      <div className="mt-2 flex justify-between text-[10px] uppercase tracking-wide text-muted/70 pb-1">
        <span>Symbol</span>
        <span className="flex gap-3">
          <span>Price</span>
          <span className="w-20 text-right">{metricHeader(s.value_label)}</span>
        </span>
      </div>
      <div className="flex flex-col">
        {s.items.slice(0, 6).map((it) => (
          <ScreenRow key={it.code} item={it} screen={s} />
        ))}
      </div>
      {s.items.length >= 6 && (
        <Link
          to={`/markets/${s.key}`}
          className="block text-center text-[11px] text-accent mt-2 pt-2 border-t border-border/60"
        >
          View more →
        </Link>
      )}
    </div>
  );
}

export function Markets() {
  const [data, setData] = useState<ScreensResponse | null>(null);
  const [q, setQ] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
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
  const live = data.screens.filter((s) => s.items.length > 0);

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
        <div className="text-[11px] uppercase tracking-wide text-muted">
          Discover
        </div>
        {data.as_of && (
          <div className="text-[10px] text-muted">as of {data.as_of} close</div>
        )}
      </div>

      {GROUPS.map((g) => {
        const items = live.filter((s) => s.group === g.id);
        if (!items.length) return null;
        if (g.advanced) {
          return (
            <div key={g.id} className="flex flex-col gap-3">
              <button
                onClick={() => setShowAdvanced((v) => !v)}
                className="text-[11px] uppercase tracking-wide text-muted text-left px-1"
              >
                {showAdvanced ? "▾" : "▸"} {g.label}
              </button>
              {showAdvanced &&
                items.map((s) => <ScreenCard key={s.key} s={s} />)}
            </div>
          );
        }
        return (
          <div key={g.id} className="flex flex-col gap-3">
            <div className="flex items-center justify-between px-1">
              <div className="text-[11px] uppercase tracking-wide text-muted">{g.label}</div>
              <Link to={`/markets/${items[0].key}`} className="text-[11px] text-accent">
                View more →
              </Link>
            </div>
            {items.map((s) => (
              <ScreenCard key={s.key} s={s} />
            ))}
          </div>
        );
      })}

      <p className="text-[10px] text-muted px-1 pb-2">
        Computed from end-of-day prices · descriptive screens, not
        recommendations.
      </p>
    </div>
  );
}
