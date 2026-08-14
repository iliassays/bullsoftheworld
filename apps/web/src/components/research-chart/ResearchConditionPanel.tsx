import type {
  PublicResearchChart,
  ResearchChartCondition,
  ResearchConditionKey,
  ResearchConditionState,
} from "../../lib/api";
import type { Lang } from "../../lib/i18n";
import {
  checkLabel,
  checkStateLabel,
  conditionStateLabel,
  conditionSummary,
  conditionText,
  formatCheckValue,
  researchChartCopy,
} from "../../lib/research-chart";
import { useTenantConfig } from "../../lib/tenant";

const STATE_TONE: Record<ResearchConditionState, string> = {
  observed: "border-up/40 bg-up/10 text-up",
  not_observed: "border-border bg-card text-muted",
  unavailable: "border-warn/40 bg-warn/10 text-warn",
};

function StateDot({ state }: { state: ResearchConditionState }) {
  const tone =
    state === "observed" ? "bg-up" : state === "unavailable" ? "bg-warn" : "bg-muted";
  return <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${tone}`} />;
}

function formatDate(value: string | null, lang: Lang) {
  if (!value) return "—";
  return new Intl.DateTimeFormat(lang === "bn" ? "bn-BD" : "en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T12:00:00Z`));
}

export function ResearchConditionTabs({
  conditions,
  lang,
  selected,
  onSelect,
}: {
  conditions: ResearchChartCondition[];
  lang: Lang;
  selected: ResearchConditionKey;
  onSelect: (key: ResearchConditionKey) => void;
}) {
  const copy = researchChartCopy(lang);
  return (
    <div>
      <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-muted">
        {copy.layers}
      </div>
      <div className="flex gap-1.5 overflow-x-auto pb-1" role="tablist" aria-label={copy.layers}>
        {conditions.map((condition) => {
          const active = selected === condition.key;
          return (
            <button
              key={condition.key}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => onSelect(condition.key)}
              className={`flex shrink-0 cursor-pointer items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs font-semibold transition-colors ${
                active
                  ? "border-accent bg-accent/10 text-text"
                  : "border-border bg-card text-muted hover:border-accent/60 hover:text-text"
              }`}
            >
              <StateDot state={condition.state} />
              {conditionText(condition, lang).title}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function ResearchConditionInspector({
  condition,
  lang,
  research,
  priceHasNewerBar,
}: {
  condition: ResearchChartCondition;
  lang: Lang;
  research: PublicResearchChart;
  priceHasNewerBar: boolean;
}) {
  const copy = researchChartCopy(lang);
  const { config } = useTenantConfig();
  const text = conditionText(condition, lang);
  const latestTransition = condition.transitions[condition.transitions.length - 1];
  const atlasUrl = new URL("/conditions", config.research_site_url);
  atlasUrl.searchParams.set("condition", condition.key);

  return (
    <section className="mt-3 border-t border-border pt-3" aria-labelledby="research-condition-title">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 id="research-condition-title" className="text-sm font-semibold text-text">
            {text.title}
          </h3>
          <p className="mt-0.5 text-xs leading-relaxed text-muted">
            {conditionSummary(condition, lang)}
          </p>
        </div>
        <span
          className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[11px] font-semibold ${STATE_TONE[condition.state]}`}
        >
          <StateDot state={condition.state} />
          {conditionStateLabel(condition.state, lang)}
        </span>
      </div>

      <div className="mt-3 divide-y divide-border border-y border-border">
        {condition.checks.map((check) => (
          <div
            key={`${condition.key}-${check.fact_key}-${check.label}`}
            className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 py-2 text-xs sm:grid-cols-[minmax(0,1fr)_88px_108px_auto]"
          >
            <span className="min-w-0 text-text">{checkLabel(check, lang)}</span>
            <span className="tnum text-right font-semibold text-text">{formatCheckValue(check)}</span>
            <span className="text-right text-muted">
              <span className="sm:hidden">{copy.threshold}: </span>
              {check.expected}
            </span>
            <span
              className={`text-right font-semibold ${
                check.passed === true
                  ? "text-up"
                  : check.passed === false
                    ? "text-down"
                    : "text-warn"
              }`}
            >
              {checkStateLabel(check, lang)}
            </span>
          </div>
        ))}
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted">
        <span>
          {copy.dataThrough} <strong className="font-semibold text-text">{formatDate(research.as_of_date, lang)}</strong>{" "}
          · {copy.completedClose}
        </span>
        <span>
          {copy.history}: {condition.transitions.length || copy.noHistory}
          {latestTransition ? ` · ${formatDate(latestTransition.date, lang)}` : ""}
        </span>
      </div>
      {priceHasNewerBar && <p className="mt-1 text-[11px] text-warn">{copy.currentPriceNote}</p>}

      <details className="mt-3 border-t border-border pt-2 text-xs">
        <summary className="cursor-pointer select-none font-semibold text-text">
          {copy.calculations}
        </summary>
        <div className="mt-2 grid gap-2 leading-relaxed text-muted sm:grid-cols-2">
          <p><strong className="text-text">{copy.why}:</strong> {text.why}</p>
          <p><strong className="text-text">{copy.limitation}:</strong> {text.limitation}</p>
        </div>
      </details>

      {research.volume_profile.status === "unavailable" && (
        <details className="mt-2 border-t border-border pt-2 text-xs">
          <summary className="cursor-pointer select-none font-semibold text-text">
            {copy.profile}
          </summary>
          <p className="mt-2 leading-relaxed text-muted">{copy.profileUnavailable}</p>
        </details>
      )}

      <a
        className="mt-3 inline-flex cursor-pointer items-center text-xs font-semibold text-accent hover:underline"
        href={atlasUrl.toString()}
      >
        {lang === "bn" ? "Atlas-এ এই শর্তের সব শেয়ার দেখুন ↗" : "See all securities with this condition in Atlas ↗"}
      </a>

      <p className="mt-3 border-t border-border pt-2 text-[10px] leading-relaxed text-muted">
        {copy.disclaimer} · {research.methodology_version}
      </p>
    </section>
  );
}
