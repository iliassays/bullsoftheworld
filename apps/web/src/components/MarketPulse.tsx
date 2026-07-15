import { useEffect, useState } from "react";
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

function Cell({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] uppercase tracking-wide text-muted leading-snug">{label}</div>
      <div className="text-sm font-bold tnum truncate">{value}</div>
      {sub && <div className="text-[10px] leading-snug text-muted">{sub}</div>}
    </div>
  );
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
  const sectorSub =
    pulse.weak_sector && pulse.weak_sector_change != null
      ? `${t("marketPulse.weak")} ${pulse.weak_sector} ${signed(pulse.weak_sector_change)}`
      : undefined;
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

      {/* The index level is the one number a reader orients on before anything else on this
          card — promoted to its own hero line instead of sitting the same size as turnover
          or breadth in the stat grid below. */}
      <div className="mt-3 flex items-baseline gap-2.5">
        <span className="text-[26px] font-extrabold tnum leading-none">
          {(pulse.benchmark_close ?? pulse.dsex) == null
            ? "—"
            : (pulse.benchmark_close ?? pulse.dsex)!.toLocaleString(undefined, {
                maximumFractionDigits: 2,
              })}
        </span>
        {benchmarkChange != null && (
          <span className={`text-sm font-bold tnum ${benchmarkChange >= 0 ? "text-up" : "text-down"}`}>
            {signed(benchmarkChange)}
          </span>
        )}
      </div>
      <div className="text-[10px] text-muted mt-0.5">
        {liveContext
          ? `${pulse.benchmark_label ?? config.benchmark_label} · ${t("marketPulse.previousClose")} (${closeDate})${benchmarkChange != null ? ` · ${t("marketPulse.previousSession")}` : ""}`
          : (pulse.benchmark_label ?? config.benchmark_label)}
      </div>

      <div className="grid grid-cols-2 gap-3 mt-3">
        <Cell
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
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-wide text-muted">
            {pulse.coverage_complete ? t("marketPulse.breadth") : t("marketPulse.trackedBreadth")}
          </div>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="text-sm font-bold text-up tnum">{pulse.advancers}▲</span>
            <span className="text-sm font-bold text-down tnum">{pulse.decliners}▼</span>
            <span className="text-xs text-muted tnum">
              {pulse.unchanged} {t("marketPulse.unchanged")}
            </span>
          </div>
          <div className="mt-1.5 h-1.5 rounded-full overflow-hidden bg-border">
            <div className="h-full bg-up" style={{ width: `${breadthPct}%` }} />
          </div>
        </div>
        <div className="col-span-2">
          <Cell
            label={t("marketPulse.sectors")}
            value={
              pulse.top_sector && pulse.top_sector_change != null
                ? `${pulse.top_sector} ${signed(pulse.top_sector_change)}`
                : "—"
            }
            sub={sectorSub}
          />
        </div>
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
