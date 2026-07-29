import { useEffect, useState } from "react";
import {
  api,
  type DailyShortlistPerformance,
  type ShortlistHorizonPerformance,
} from "../lib/api";
import { type Lang, useLang } from "../lib/i18n";

const HORIZONS = [1, 3, 5, 10] as const;

function count(value: number, lang: Lang): string {
  return new Intl.NumberFormat(lang === "bn" ? "bn-BD" : "en-GB").format(value);
}

function compactDate(value: string, lang: Lang): string {
  return new Intl.DateTimeFormat(lang === "bn" ? "bn-BD" : "en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(new Date(`${value}T12:00:00Z`));
}

function signedPct(value: number | null | undefined, digits = 2): string {
  if (value == null) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

function valueClass(value: number | null | undefined): string {
  if (value == null || value === 0) return "text-muted";
  return value > 0 ? "text-up" : "text-down";
}

function statusPresentation(
  status: DailyShortlistPerformance["edge_status"],
  t: (key: string) => string,
): { label: string; className: string } {
  switch (status) {
    case "positive_diagnostic_requires_forward_validation":
      return {
        label: t("shortlist.performanceDiagnostic"),
        className: "border-accent/40 bg-accent/10 text-accent",
      };
    case "positive_but_unproven":
      return {
        label: t("shortlist.performanceUnproven"),
        className: "border-accent/40 bg-accent/10 text-accent",
      };
    case "no_observed_excess":
      return {
        label: t("shortlist.performanceNoExcess"),
        className: "border-down/30 bg-down/8 text-down",
      };
    default:
      return {
        label: t("shortlist.performanceInsufficient"),
        className: "border-border bg-card text-muted",
      };
  }
}

function metricFor(
  horizons: ShortlistHorizonPerformance[],
  sessions: number,
): ShortlistHorizonPerformance | undefined {
  return horizons.find((item) => item.sessions === sessions);
}

export function ShortlistPerformanceEvidence() {
  const { t, lang } = useLang();
  const [data, setData] = useState<DailyShortlistPerformance | null | undefined>();

  useEffect(() => {
    let live = true;
    api
      .dailyShortlistPerformance()
      .then((value) => {
        if (live) setData(value);
      })
      .catch(() => {
        if (live) setData(null);
      });
    return () => {
      live = false;
    };
  }, []);

  if (data === undefined) {
    return <div className="h-28 animate-pulse border-t border-border bg-card/40" aria-hidden />;
  }
  if (data === null) {
    return (
      <p className="border-t border-border pt-3 text-[11px] text-muted">
        {t("shortlist.performanceUnavailable")}
      </p>
    );
  }

  const cohort = data.cohorts.find((item) => item.key === "independent_episodes");
  if (!cohort) return null;
  const primary = metricFor(cohort.horizons, data.primary_horizon_sessions);
  const auditIssues =
    data.integrity.missing_selection_bars +
    data.integrity.close_mismatches +
    data.integrity.move_mismatches +
    data.integrity.incomplete_sessions +
    data.integrity.invalid_rank_sessions;
  const status = statusPresentation(data.edge_status, t);
  const range =
    cohort.first_selection_date && cohort.last_selection_date
      ? t("shortlist.performanceRange")
          .replace("{from}", compactDate(cohort.first_selection_date, lang))
          .replace("{to}", compactDate(cohort.last_selection_date, lang))
      : null;

  return (
    <section className="border-t border-border pt-3" aria-labelledby="shortlist-performance-title">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 id="shortlist-performance-title" className="text-xs font-semibold text-text">
            {t("shortlist.performanceTitle")}
          </h3>
          <p className="mt-0.5 text-[10px] text-muted">
            {t("shortlist.performanceSubtitle")}
          </p>
        </div>
        <span
          className={`rounded-md border px-2 py-1 text-[10px] font-semibold ${status.className}`}
        >
          {status.label}
        </span>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] text-muted">
        <strong className="font-semibold text-text">
          {t("shortlist.performanceEpisodes").replace(
            "{n}",
            count(data.independent_episodes, lang),
          )}
        </strong>
        {range && <span>{range}</span>}
      </div>

      <div className="mt-2 overflow-hidden rounded-lg border border-border">
        <div className="grid grid-cols-[2.7rem_repeat(3,minmax(0,1fr))] bg-card px-2 py-1.5 text-[9px] font-semibold text-muted">
          <span>{t("shortlist.performanceHorizon")}</span>
          <span className="text-right">{t("shortlist.performanceMedian")}</span>
          <span className="text-right">{t("shortlist.performancePositive")}</span>
          <span className="text-right">{t("shortlist.performanceVsIndex")}</span>
        </div>
        {HORIZONS.map((sessions) => {
          const metric = metricFor(cohort.horizons, sessions);
          return (
            <div
              key={sessions}
              className="grid grid-cols-[2.7rem_repeat(3,minmax(0,1fr))] border-t border-border px-2 py-2 text-[11px] tabular-nums"
            >
              <strong>
                {count(sessions, lang)}
                {lang === "bn" ? "স" : "S"}
              </strong>
              <span className={`text-right font-semibold ${valueClass(metric?.median_return_pct)}`}>
                {signedPct(metric?.median_return_pct)}
              </span>
              <span className="text-right">
                {metric?.positive_rate_pct == null
                  ? "—"
                  : `${metric.positive_rate_pct.toFixed(1)}%`}
              </span>
              <span
                className={`text-right font-semibold ${valueClass(metric?.mean_excess_return_pct)}`}
              >
                {signedPct(metric?.mean_excess_return_pct)}
              </span>
            </div>
          );
        })}
      </div>

      {primary && (
        <div className="mt-2 grid gap-1 text-[10px] leading-relaxed text-muted">
          <p>
            {t("shortlist.performanceCoverage")
              .replace("{observed}", count(primary.observations, lang))
              .replace("{matured}", count(primary.matured_appearances, lang))}
            {primary.coverage_pct != null ? ` · ${primary.coverage_pct.toFixed(1)}%` : ""}
          </p>
          <p>
            {t("shortlist.performanceBenchmarkCoverage")
              .replace("{benchmark}", count(primary.benchmark_observations, lang))
              .replace("{observed}", count(primary.observations, lang))}
          </p>
          <p>
            {t("shortlist.performanceNextOpen")
              .replace("{n}", count(primary.sessions, lang))
              .replace("{value}", signedPct(primary.next_open_median_return_pct))
              .replace("{count}", count(primary.next_open_observations, lang))}
          </p>
        </div>
      )}

      <div className="mt-3 border-t border-border pt-2">
        <div className="flex flex-wrap items-center justify-between gap-1 text-[10px]">
          <strong>{t("shortlist.performanceAudit")}</strong>
          <span className={auditIssues === 0 ? "text-up" : "text-down"}>
            {auditIssues === 0
              ? t("shortlist.performanceAuditClean")
                  .replace(
                    "{closes}",
                    count(data.integrity.matched_selection_closes, lang),
                  )
                  .replace("{moves}", count(data.integrity.matched_selection_moves, lang))
              : t("shortlist.performanceAuditIssue").replace(
                  "{n}",
                  count(auditIssues, lang),
                )}
          </span>
        </div>
        <p className="mt-1 text-[10px] text-muted">
          {t("shortlist.performanceEvidenceMix")
            .replace("{forward}", count(data.forward_appearances, lang))
            .replace("{reconstructed}", count(data.reconstructed_appearances, lang))}
        </p>
      </div>

      <details className="mt-2 border-t border-border pt-2 text-[10px] text-muted">
        <summary className="cursor-pointer font-semibold text-text">
          {t("shortlist.performanceMethod")}
        </summary>
        <p className="mt-1.5 leading-relaxed">{t("shortlist.performanceMethodCopy")}</p>
      </details>
    </section>
  );
}
