import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type TrendingReason, type TrendingStock } from "../lib/api";
import { useLang } from "../lib/i18n";
import { CompanyLogo } from "./CompanyLogo";
import { FreshnessTag } from "./FreshnessTag";
import { InfoTip } from "./InfoTip";
import { Pct } from "./ui";

function takaMn(mn: number | null | undefined): string {
  if (mn == null) return "—";
  if (mn >= 10)
    return `৳${(mn / 10).toLocaleString(undefined, { maximumFractionDigits: mn >= 100 ? 0 : 1 })}Cr`;
  return `৳${(mn * 10).toLocaleString(undefined, { maximumFractionDigits: mn >= 1 ? 0 : 1 })}L`;
}

// The precomputed daily activity ranking (see ingestion.trending). The frontend just renders the
// ordered list + the language-neutral reason chips. Descriptive — activity, never a recommendation.
//
// `asOf` is optional and comes from the PARENT page's own /screens fetch (Markets.tsx) rather
// than a new backend field here — run_trending computes this ranking in the same nightly EOD
// chain as refresh_analytics (13:15/13:25 UTC), so they share the same calendar date in practice.
// Each row's % move is frozen at that same computation, not the live 15-min quote (only the
// price shown alongside is live) — the same "which timestamp does this number mean" gap a user
// flagged on the Ideas page.
export function WatchToday({ asOf }: { asOf?: string | null } = {}) {
  const { t } = useLang();
  const [rows, setRows] = useState<TrendingStock[] | null>(null);

  useEffect(() => {
    api
      .trendingStocks(15)
      .then(setRows)
      .catch(() => setRows([]));
  }, []);

  const fill = (key: string, vars: Record<string, string | number>) =>
    t(key).replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? ""));

  const reasonText = (r: TrendingReason): string => {
    switch (r.kind) {
      case "volume":
        return fill("watch.r.volume", { mult: r.mult ?? "" });
      case "turnover":
        return r.mult
          ? fill("watch.r.turnoverMult", { cr: r.cr ?? "", mult: r.mult })
          : fill("watch.r.turnover", { cr: r.cr ?? "" });
      case "near_high":
        return t("watch.r.near_high");
      case "near_low":
        return t("watch.r.near_low");
      case "move":
        return fill("watch.r.move", { pct: `${(r.pct ?? 0) > 0 ? "+" : ""}${r.pct}` });
      case "limit_up":
        return t("watch.r.limit_up");
      case "limit_down":
        return t("watch.r.limit_down");
      default:
        return "";
    }
  };

  if (rows === null)
    return <div className="bg-surface border border-border rounded-2xl p-4 animate-pulse h-40" />;
  if (rows.length === 0) return null; // nothing ranked yet (e.g. before the first nightly run)

  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <div className="flex items-center gap-2">
        <span aria-hidden>🔥</span>
        <span className="font-bold text-sm">{t("watch.title")}</span>
        <InfoTip text={t("watch.subtitle")} lessonId="active_today" />
        {asOf && <FreshnessTag asOf={asOf} className="ml-auto" />}
      </div>
      <p className="text-[11px] text-muted mt-0.5">{t("watch.subtitle")}</p>

      <div className="mt-3 flex flex-col divide-y divide-border">
        {rows.map((s, i) => (
          <Link key={s.code} to={`/s/${s.code}`} className="flex gap-2.5 py-2.5 items-start">
            <span className="text-[11px] text-muted w-4 text-center pt-0.5">{i + 1}</span>
            <CompanyLogo code={s.code} size={22} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-bold text-[13px]">${s.code}</span>
                {s.heating_up && (
                  <span className="text-[10px] text-muted font-semibold shrink-0">
                    🔥 {t("watch.heating")}
                  </span>
                )}
                <span className="ml-auto text-xs font-semibold shrink-0">
                  <Pct value={s.change_pct} />
                </span>
              </div>
              <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1">
                {s.reasons.map((r, j) => (
                  <span key={j} className="text-[11px] text-muted">
                    {reasonText(r)}
                  </span>
                ))}
              </div>
              {(s.adtv_mn != null || s.category) && (
                <div className="mt-1 text-[10px] text-muted leading-snug">
                  {s.adtv_mn != null && (
                    <>
                      {t("liq.adtv")} {takaMn(s.adtv_mn)}
                      {s.safe_order_mn != null && (
                        <>
                          {" · "}
                          {t("liq.size5")} {takaMn(s.safe_order_mn)}
                        </>
                      )}
                    </>
                  )}
                  {s.category && (
                    <>
                      {s.adtv_mn != null ? " · " : ""}
                      {t("liq.cat")} {s.category}
                    </>
                  )}
                </div>
              )}
            </div>
          </Link>
        ))}
      </div>

      <p className="text-[10px] text-muted mt-2">{t("watch.footer")}</p>
    </div>
  );
}
