import { useEffect, useState } from "react";
import { api, type MarketPulse as MarketPulseData } from "../lib/api";
import { FreshnessTag } from "./FreshnessTag";
import { useLang } from "../lib/i18n";
import { Pct } from "./ui";
import { formatCurrencyMillions } from "../lib/market";
import { useTenantConfig } from "../lib/tenant";

const riskClass: Record<MarketPulseData["risk_mode"], string> = {
  risk_on: "text-up bg-up/10 border-up/30",
  mixed: "text-accent bg-accent/10 border-accent/30",
  defensive: "text-down bg-down/10 border-down/30",
};

function fmtCr(n: number | null | undefined) {
  if (n == null) return "—";
  return `৳${n.toLocaleString(undefined, { maximumFractionDigits: n >= 100 ? 0 : 1 })}cr`;
}

function signed(n: number | null | undefined) {
  if (n == null) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
}

function Cell({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] uppercase tracking-wide text-muted truncate">{label}</div>
      <div className="text-sm font-bold tnum truncate">{value}</div>
      {sub && <div className="text-[10px] text-muted truncate">{sub}</div>}
    </div>
  );
}

export function MarketPulse() {
  const { t, lang } = useLang();
  const { config } = useTenantConfig();
  const [pulse, setPulse] = useState<MarketPulseData | null>(null);

  useEffect(() => {
    api
      .marketPulse()
      .then(setPulse)
      .catch(() => setPulse(null));
  }, []);

  if (!pulse) return null;
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
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-bold text-sm">{t("marketPulse.title")}</div>
          <div className="text-[11px] text-muted">{t("marketPulse.subtitle")}</div>
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          <span
            className={`border rounded-full px-2.5 py-1 text-[11px] font-semibold ${riskClass[pulse.risk_mode]}`}
          >
            {!pulse.coverage_complete && `${t("marketPulse.tracked")} · `}
            {t(`risk.${pulse.risk_mode}`)}
          </span>
          {/* DSEX is EOD-anchored (one row/day) even though breadth/sectors below track the
              live 15-min quote poll — this card mixes both, so the anchor is worth calling out
              here specifically, not just relying on the page-level FreshnessTag elsewhere. */}
          <FreshnessTag
            asOf={pulse.as_of}
            quoteAsOf={pulse.quote_as_of}
            priceMode="mixed"
            className=""
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 mt-3">
        <Cell
          label={pulse.benchmark_label ?? config.benchmark_label}
          value={
            (pulse.benchmark_close ?? pulse.dsex) == null
              ? "—"
              : (pulse.benchmark_close ?? pulse.dsex)!.toLocaleString(undefined, {
                  maximumFractionDigits: 2,
                })
          }
          sub={
            benchmarkChange == null
              ? undefined
              : signed(benchmarkChange)
          }
        />
        <Cell
          label={t("marketPulse.turnover")}
          value={
            pulse.turnover_mn == null
              ? fmtCr(pulse.turnover_cr)
              : formatCurrencyMillions(pulse.turnover_mn)
          }
          sub={
            pulse.turnover_vs_20d == null
              ? undefined
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
            <span className="text-xs text-muted tnum">{pulse.unchanged} flat</span>
          </div>
          <div className="mt-1.5 h-1.5 rounded-full overflow-hidden bg-border">
            <div className="h-full bg-up" style={{ width: `${breadthPct}%` }} />
          </div>
        </div>
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

      <p className="mt-3 text-[10px] text-muted">
        {t("marketPulse.footer")}{" "}
        {benchmarkChange != null && <Pct value={benchmarkChange} />}
      </p>
      <p className={`mt-1 text-[10px] ${pulse.coverage_complete ? "text-muted" : "text-accent"}`}>
        {coverageText}. {pulse.coverage_complete ? t("marketPulse.coverageFull") : t("marketPulse.coveragePartial")}
      </p>
    </div>
  );
}
