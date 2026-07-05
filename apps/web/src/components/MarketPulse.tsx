import { useEffect, useState } from "react";
import { api, type MarketPulse as MarketPulseData } from "../lib/api";
import { useLang } from "../lib/i18n";
import { Pct } from "./ui";

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
  const { t } = useLang();
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
  const sectorSub =
    pulse.weak_sector && pulse.weak_sector_change != null
      ? `${t("marketPulse.weak")} ${pulse.weak_sector} ${signed(pulse.weak_sector_change)} ${t("pct.1d")}`
      : undefined;

  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-bold text-sm">{t("marketPulse.title")}</div>
          <div className="text-[11px] text-muted">{t("marketPulse.subtitle")}</div>
        </div>
        <span
          className={`shrink-0 border rounded-full px-2.5 py-1 text-[11px] font-semibold ${riskClass[pulse.risk_mode]}`}
        >
          {t(`risk.${pulse.risk_mode}`)}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3 mt-3">
        <Cell
          label="DSEX"
          value={pulse.dsex == null ? "—" : pulse.dsex.toLocaleString(undefined, { maximumFractionDigits: 2 })}
          sub={
            pulse.dsex_change_pct == null
              ? undefined
              : `${signed(pulse.dsex_change_pct)} ${t("pct.1d")}`
          }
        />
        <Cell
          label={t("marketPulse.turnover")}
          value={fmtCr(pulse.turnover_cr)}
          sub={
            pulse.turnover_vs_20d == null
              ? undefined
              : `${pulse.turnover_vs_20d.toFixed(1)}x ${t("marketPulse.vs20d")}`
          }
        />
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-wide text-muted">{t("marketPulse.breadth")}</div>
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
              ? `${pulse.top_sector} ${signed(pulse.top_sector_change)} ${t("pct.1d")}`
              : "—"
          }
          sub={sectorSub}
        />
      </div>

      <p className="mt-3 text-[10px] text-muted">
        {t("marketPulse.footer")}{" "}
        {pulse.dsex_change_pct != null && <Pct value={pulse.dsex_change_pct} period="1d" />}
      </p>
    </div>
  );
}
