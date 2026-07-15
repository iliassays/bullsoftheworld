import { type ReactNode, useEffect, useRef, useState } from "react";
import { api, type MarketPulse as MarketPulseData } from "../lib/api";
import { useLang } from "../lib/i18n";
import { formatCurrencyMillions, marketUiFromConfig } from "../lib/market";
import { useTenantConfig } from "../lib/tenant";
import { formatMarketTime } from "../lib/time";

const riskClass: Record<MarketPulseData["risk_mode"], string> = {
  risk_on: "text-up bg-up/10 border-up/30",
  mixed: "text-accent bg-accent/10 border-accent/30",
  defensive: "text-down bg-down/10 border-down/30",
};

function signed(n: number | null | undefined) {
  if (n == null) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
}

// Bento tile: each stat gets its own bounded card so tile size (not reading order) carries
// priority — the hero index tile spans the full row, satellites sit two-up beneath it.
function Tile({
  label,
  value,
  sub,
  valueClass = "",
  span2 = false,
  children,
}: {
  label: string;
  value?: string;
  sub?: string;
  valueClass?: string;
  span2?: boolean;
  children?: ReactNode;
}) {
  return (
    <div className={`min-w-0 rounded-xl bg-card border border-border p-2.5 ${span2 ? "col-span-2" : ""}`}>
      <div className="text-[10px] uppercase tracking-wide text-muted leading-snug">{label}</div>
      {value != null && (
        <div className={`text-sm font-bold tnum truncate mt-0.5 ${valueClass}`}>{value}</div>
      )}
      {children}
      {sub && <div className="text-[10px] leading-snug text-muted mt-0.5">{sub}</div>}
    </div>
  );
}

// Rolls the hero number to its new value when the pulse refreshes. Deliberately NOT a count-up
// from zero on first paint — the first render shows the real number immediately (never animate
// fake states into data), and the roll only plays on a subsequent refresh, where motion carries
// real information ("this just updated"). Skipped entirely under prefers-reduced-motion.
function useRollingNumber(target: number | null, duration = 600): number | null {
  const [value, setValue] = useState(target);
  const fromRef = useRef<number | null>(null);
  useEffect(() => {
    if (target == null) {
      fromRef.current = null;
      setValue(null);
      return;
    }
    const from = fromRef.current;
    fromRef.current = target;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced || from == null || from === target) {
      setValue(target);
      return;
    }
    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const progress = Math.min(1, (now - start) / duration);
      const eased = 1 - (1 - progress) ** 3;
      setValue(from + (target - from) * eased);
      if (progress < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration]);
  return value;
}

function sessionDate(value: string | null | undefined, lang: "en" | "bn") {
  if (!value) return "—";
  return new Intl.DateTimeFormat(lang === "bn" ? "bn-BD" : "en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(new Date(`${value.slice(0, 10)}T12:00:00Z`));
}

export function MarketPulse() {
  const { t, lang } = useLang();
  const { config } = useTenantConfig();
  const [pulse, setPulse] = useState<MarketPulseData | null>(null);

  useEffect(() => {
    let active = true;
    const load = () => {
      api
        .marketPulse()
        .then((next) => active && setPulse(next))
        .catch(() => active && setPulse(null));
    };
    const refreshWhenVisible = () => {
      if (document.visibilityState === "visible") load();
    };

    load();
    const timer = window.setInterval(load, 15 * 60 * 1000);
    document.addEventListener("visibilitychange", refreshWhenVisible);
    return () => {
      active = false;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
    };
  }, []);

  // Hook must run unconditionally (before the null return); it receives null until data lands.
  const rolledIndex = useRollingNumber(pulse ? (pulse.benchmark_close ?? pulse.dsex) : null);

  if (!pulse) return null;
  const bn = lang === "bn";
  const marketUi = marketUiFromConfig(config);
  const liveContext = pulse.data_status !== "official_close";
  const closeDate = sessionDate(pulse.close_as_of, lang);
  const quoteTime = formatMarketTime(pulse.quote_as_of, marketUi);
  const statusText =
    pulse.data_status === "stale"
      ? bn
        ? `ডেটা আপডেট দেরি হচ্ছে · সর্বশেষ ${quoteTime}`
        : `Data refresh is late · latest ${quoteTime}`
      : pulse.data_status === "intraday_delayed"
        ? bn
          ? `আজকের বাজার · ১৫ মিনিট বিলম্বিত · আপডেট ${quoteTime}`
          : `Today's market · 15-minute delayed · updated ${quoteTime}`
        : pulse.data_status === "provisional_close"
          ? bn
            ? `ক্লোজ-পরবর্তী প্রাথমিক চিত্র · আপডেট ${quoteTime}`
            : `Provisional post-close snapshot · updated ${quoteTime}`
          : bn
            ? `সম্পূর্ণ সেশন · ${closeDate} ক্লোজ`
            : `Completed session · ${closeDate} close`;
  const totalBreadth = pulse.advancers + pulse.decliners || 1;
  const breadthPct = (pulse.advancers / totalBreadth) * 100;
  const benchmarkChange = pulse.benchmark_change_pct ?? pulse.dsex_change_pct;
  const coverageText = pulse.coverage_complete
    ? lang === "bn"
      ? `${pulse.published_symbols.toLocaleString()}টি ${config.exchange_code} সিকিউরিটি`
      : `${pulse.published_symbols.toLocaleString()} ${config.exchange_code} securities`
    : lang === "bn"
      ? `${pulse.eligible_symbols.toLocaleString()}টি সক্রিয় সিকিউরিটির মধ্যে ${pulse.published_symbols.toLocaleString()}টি প্রকাশিত`
      : `${pulse.published_symbols.toLocaleString()} published of ${pulse.eligible_symbols.toLocaleString()} active securities`;

  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="font-bold text-sm">{t("marketPulse.title")}</div>
        <span
          className={`shrink-0 border rounded-full px-2.5 py-1 text-[11px] font-semibold whitespace-nowrap ${riskClass[pulse.risk_mode]}`}
        >
          {!pulse.coverage_complete && `${t("marketPulse.tracked")} · `}
          {t(`risk.${pulse.risk_mode}`)}
        </span>
      </div>
      <div className="text-[11px] text-muted mt-0.5">{t("marketPulse.subtitle")}</div>
      <div
        className={`mt-2 text-[10px] leading-snug ${pulse.data_status === "stale" ? "font-semibold text-down" : liveContext ? "font-semibold text-accent" : "text-muted"}`}
        aria-live="polite"
      >
        {statusText}
      </div>

      {/* Bento deck: the index is the biggest tile because it's the first question; breadth,
          turnover and sector leadership are satellites. Tile size — not stacking order —
          carries priority. */}
      <div className="grid grid-cols-2 gap-2 mt-3">
        <div className="col-span-2 min-w-0 rounded-xl bg-card border border-border p-3">
          <div className="text-[10px] uppercase tracking-wide text-muted leading-snug">
            {liveContext
              ? `${pulse.benchmark_label ?? config.benchmark_label} · ${t("marketPulse.previousClose")} (${closeDate})`
              : (pulse.benchmark_label ?? config.benchmark_label)}
          </div>
          <div className="mt-1 flex items-baseline gap-2.5">
            <span className="text-[28px] font-extrabold tnum leading-none">
              {rolledIndex == null
                ? "—"
                : rolledIndex.toLocaleString(undefined, { maximumFractionDigits: 2 })}
            </span>
            {benchmarkChange != null && (
              <span
                className={`text-sm font-bold tnum ${benchmarkChange >= 0 ? "text-up" : "text-down"}`}
              >
                {signed(benchmarkChange)}
                {liveContext && (
                  <span className="ml-1.5 font-normal text-[10px] text-muted">
                    {t("marketPulse.previousSession")}
                  </span>
                )}
              </span>
            )}
          </div>
        </div>
        <Tile label={pulse.coverage_complete ? t("marketPulse.breadth") : t("marketPulse.trackedBreadth")}>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="text-sm font-bold text-up tnum">{pulse.advancers}▲</span>
            <span className="text-sm font-bold text-down tnum">{pulse.decliners}▼</span>
          </div>
          <div className="mt-1.5 h-1.5 rounded-full overflow-hidden bg-border">
            <div className="h-full bg-up" style={{ width: `${breadthPct}%` }} />
          </div>
          <div className="text-[10px] leading-snug text-muted mt-1">
            {pulse.unchanged} {t("marketPulse.unchanged")}
          </div>
        </Tile>
        <Tile
          label={
            pulse.turnover_is_partial
              ? pulse.turnover_is_estimated
                ? t("marketPulse.estimatedTurnoverSoFar")
                : t("marketPulse.turnoverSoFar")
              : t("marketPulse.turnover")
          }
          value={formatCurrencyMillions(pulse.turnover_mn, marketUi)}
          sub={
            pulse.turnover_vs_20d == null
              ? undefined
              : pulse.turnover_is_partial
                ? `${pulse.turnover_vs_20d.toFixed(1)}x ${t("marketPulse.ofFullSessionAvg")}${pulse.turnover_is_estimated ? ` · ${t("marketPulse.estimate")}` : ""}`
                : `${pulse.turnover_vs_20d.toFixed(1)}x ${t("marketPulse.vs20d")}`
          }
        />
        {pulse.top_sector && pulse.top_sector_change != null && (
          <Tile
            label={t("marketPulse.leading")}
            value={pulse.top_sector}
            valueClass="text-up"
            sub={signed(pulse.top_sector_change)}
            span2={!(pulse.weak_sector && pulse.weak_sector_change != null)}
          />
        )}
        {pulse.weak_sector && pulse.weak_sector_change != null && (
          <Tile
            label={t("marketPulse.lagging")}
            value={pulse.weak_sector}
            valueClass="text-down"
            sub={signed(pulse.weak_sector_change)}
            span2={!(pulse.top_sector && pulse.top_sector_change != null)}
          />
        )}
      </div>

      <p className="mt-3 text-[10px] text-muted">
        {liveContext ? t("marketPulse.liveFooter") : t("marketPulse.footer")}
      </p>
      <p className={`mt-1 text-[10px] ${pulse.coverage_complete ? "text-muted" : "text-accent"}`}>
        {coverageText}. {pulse.coverage_complete ? t("marketPulse.coverageFull") : t("marketPulse.coveragePartial")}
      </p>
    </div>
  );
}
