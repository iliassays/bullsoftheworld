import {
  Activity,
  Bell,
  BellOff,
  CalendarDays,
  Check,
  CircleAlert,
  ExternalLink,
  History,
  Radar,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { researchDeployment } from "../../app/deployment";
import {
  Button,
  SegmentedControl,
  SelectField,
  StatusBadge,
  type SelectOption,
} from "../../design-system";
import { useConditionScan, useConditionScannerWorkspaces, useConditionSubscription } from "./hooks";
import {
  calibrationFor,
  formatConditionValue,
  signedPercent,
  type ConditionEvidenceMode,
  type ConditionKey,
  type ConditionScan,
  type ConditionScanItem,
} from "./model";

type CapFilter = "all" | string;
type ObservationFilter = "all" | "new";

const CONDITION_OPTIONS = [
  { value: "trend_alignment", label: "Trend alignment" },
  { value: "participation_expansion", label: "Participation" },
  { value: "controlled_pullback_context", label: "Pullback context" },
] as const;

const CAP_LABELS: Record<string, string> = {
  mega: "Mega cap",
  large: "Large cap",
  mid: "Mid cap",
  small: "Small cap",
  micro: "Micro cap",
  penny: "Penny stock",
  unclassified: "Unclassified",
};

const HORIZONS = [1, 5, 20, 60] as const;

function dateLabel(value: string | null): string {
  if (!value) return "Unavailable";
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

function money(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: researchDeployment.currency,
    maximumFractionDigits: value >= 100 ? 1 : 2,
  }).format(value);
}

function valueTraded(value: number | null): string {
  if (value === null) return "Liquidity unavailable";
  const unit = researchDeployment.currency === "BDT" ? "BDT" : "$";
  return `${unit}${value.toLocaleString("en-US", { maximumFractionDigits: 1 })}m average daily value`;
}

function sampleLabel(mode: ConditionEvidenceMode): string {
  return mode === "forward" ? "Forward observations" : "Historical reconstruction";
}

function CalibrationPanel({ scan }: { scan: ConditionScan }) {
  const [mode, setMode] = useState<ConditionEvidenceMode>("reconstructed");
  const sampleCount = (evidenceMode: ConditionEvidenceMode) =>
    calibrationFor(scan.calibrations, evidenceMode, 1)?.matured ?? 0;
  const rows = HORIZONS.map((horizon) => calibrationFor(scan.calibrations, mode, horizon));
  const available = rows.some(Boolean);

  return (
    <section aria-labelledby="condition-calibration-title" className="condition-calibration">
      <header className="condition-calibration__header">
        <div>
          <span className="condition-section-label"><History aria-hidden="true" size={14} /> Evidence calibration</span>
          <h2 id="condition-calibration-title">What happened after this condition appeared?</h2>
          <p>Subsequent completed-session outcomes, separated by how the observation was collected.</p>
        </div>
        <SegmentedControl
          label="Calibration evidence mode"
          onChange={setMode}
          options={[
            { value: "reconstructed", label: "Reconstructed", count: sampleCount("reconstructed") },
            { value: "forward", label: "Forward", count: sampleCount("forward") },
          ]}
          value={mode}
        />
      </header>

      {!available ? (
        <div className="condition-calibration__empty">
          <ShieldCheck aria-hidden="true" size={20} />
          <span>
            <strong>No matured {sampleLabel(mode).toLowerCase()} yet</strong>
            <small>Atlas will populate this after enough future completed sessions exist.</small>
          </span>
        </div>
      ) : (
        <div className="condition-calibration__grid">
          {HORIZONS.map((horizon) => {
            const row = calibrationFor(scan.calibrations, mode, horizon);
            return (
              <article className="condition-calibration__horizon" key={horizon}>
                <header>
                  <span>{horizon} session{horizon === 1 ? "" : "s"}</span>
                  <small>{row ? `${row.matured.toLocaleString()} matured` : "No sample"}</small>
                </header>
                <dl>
                  <div><dt>Median close</dt><dd className={row?.medianReturnPct !== null && (row?.medianReturnPct ?? 0) < 0 ? "value-down" : ""}>{signedPercent(row?.medianReturnPct ?? null)}</dd></div>
                  <div><dt>Positive closes</dt><dd>{row?.positiveRatePct === null || row?.positiveRatePct === undefined ? "—" : `${row.positiveRatePct.toFixed(1)}%`}</dd></div>
                  <div><dt>Median vs benchmark</dt><dd>{signedPercent(row?.medianExcessReturnPct ?? null)}</dd></div>
                  <div><dt>Pending</dt><dd>{row?.pending.toLocaleString() ?? "—"}</dd></div>
                </dl>
              </article>
            );
          })}
        </div>
      )}

      <footer className="condition-calibration__footnote">
        <strong>{sampleLabel(mode)}.</strong>{" "}
        {mode === "reconstructed"
          ? "Current-universe reconstruction can omit delisted securities and count overlapping episodes; it is diagnostic, not a strategy backtest."
          : "Forward observations were recorded after the production session completed; they still exclude execution costs and portfolio constraints."}
      </footer>
    </section>
  );
}

function ObservationRow({
  item,
  selected,
  onSelect,
}: {
  item: ConditionScanItem;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      aria-pressed={selected}
      className={`condition-observation-row ${selected ? "condition-observation-row--selected" : ""}`}
      onClick={onSelect}
      type="button"
    >
      <span className="condition-observation-row__identity">
        <span>
          <strong>${item.ticker}</strong>
          {item.isNew && <StatusBadge tone="positive">New</StatusBadge>}
          {item.subscribed && <Bell aria-label="Alert enabled" size={12} />}
        </span>
        <small>{item.company}</small>
      </span>
      <span className="condition-observation-row__result">
        <strong className={item.closeReturnSinceObservationPct < 0 ? "value-down" : "value-up"}>
          {signedPercent(item.closeReturnSinceObservationPct)}
        </strong>
        <small>since {dateLabel(item.observedOn)}</small>
      </span>
      <span className="condition-observation-row__meta">
        {CAP_LABELS[item.capTier] ?? item.capTier} · {valueTraded(item.averageDailyValueMn)}
      </span>
    </button>
  );
}

function ConditionInspector({
  item,
  scan,
  workspaceId,
}: {
  item: ConditionScanItem | null;
  scan: ConditionScan;
  workspaceId: string;
}) {
  const navigate = useNavigate();
  const subscription = useConditionSubscription(workspaceId);

  if (!item) {
    return (
      <section className="condition-inspector condition-inspector--empty">
        <Radar aria-hidden="true" size={26} />
        <h2>No observation in this view</h2>
        <p>Change the date-state or capitalization filter. Atlas does not substitute another market or stale preview data.</p>
      </section>
    );
  }

  const collectionSentence = item.evidenceMode === "forward"
    ? "Atlas recorded this after the completed production session."
    : "Atlas reconstructed this from stored bars; it was not captured live on that date.";
  const followThrough = item.latestSessionDate === item.observedOn
    ? "No later completed close is available yet."
    : `The latest completed close is ${signedPercent(item.closeReturnSinceObservationPct)} from the observation close.`;

  return (
    <section aria-label={`${item.ticker} condition evidence`} className="condition-inspector">
      <header className="condition-inspector__header">
        <div>
          <span className="condition-inspector__ticker">${item.ticker}</span>
          <h2>{item.company}</h2>
          <p>{item.sector ?? "Sector unavailable"} · {CAP_LABELS[item.capTier] ?? item.capTier}</p>
        </div>
        <StatusBadge tone={item.isNew ? "positive" : "neutral"} dot>
          {item.isNew ? "New observation" : "Still observed"}
        </StatusBadge>
      </header>

      <div className="condition-inspector__story">
        <span className="condition-section-label"><Activity aria-hidden="true" size={14} /> Research story</span>
        <p>
          <strong>{item.ticker} met every registered {scan.definition.title.toLowerCase()} check on {dateLabel(item.observedOn)}.</strong>{" "}
          {scan.definition.whyItMatters} {collectionSentence} {followThrough}
        </p>
        <small>{scan.definition.limitation} This observation is not a trade signal, probability estimate, or order.</small>
      </div>

      <div className="condition-inspector__facts">
        <div><span>Observation close</span><strong>{money(item.referenceClose)}</strong><small>{dateLabel(item.observedOn)}</small></div>
        <div><span>Latest close</span><strong>{money(item.latestClose)}</strong><small>{dateLabel(item.latestSessionDate)}</small></div>
        <div><span>Close follow-through</span><strong className={item.closeReturnSinceObservationPct < 0 ? "value-down" : "value-up"}>{signedPercent(item.closeReturnSinceObservationPct)}</strong><small>not portfolio P&amp;L</small></div>
        <div><span>Trading capacity context</span><strong>{item.averageDailyValueMn === null ? "Unavailable" : `${item.averageDailyValueMn.toFixed(1)}m`}</strong><small>{researchDeployment.currency} average daily value</small></div>
      </div>

      <div className="condition-checks">
        <header>
          <div>
            <span className="condition-section-label"><Check aria-hidden="true" size={14} /> Why it appears</span>
            <h3>Actual values against the registered definition</h3>
          </div>
          <small>Completed session · {scan.definition.version}</small>
        </header>
        <div className="condition-checks__table" role="table" aria-label="Condition checks">
          <div className="condition-checks__heading" role="row">
            <span role="columnheader">Check</span><span role="columnheader">Actual</span><span role="columnheader">Required</span><span role="columnheader">Result</span>
          </div>
          {item.checks.map((check) => (
            <div className="condition-checks__row" key={check.factKey} role="row">
              <span role="cell">{check.label}</span>
              <strong role="cell">{formatConditionValue(check)}</strong>
              <span role="cell">{check.expected}</span>
              <span className={check.passed ? "condition-check--passed" : "condition-check--unavailable"} role="cell">
                {check.passed ? <><Check aria-hidden="true" size={13} /> Met</> : "Unavailable"}
              </span>
            </div>
          ))}
        </div>
      </div>

      <footer className="condition-inspector__actions">
        <Button onPress={() => navigate(`/companies/${encodeURIComponent(item.ticker)}`)} variant="secondary">
          <ExternalLink aria-hidden="true" size={14} /> Open company research
        </Button>
        <Button
          isDisabled={subscription.isPending}
          onPress={() => subscription.mutate({
            conditionKey: scan.definition.key,
            ticker: item.ticker,
            enabled: !item.subscribed,
          })}
          variant={item.subscribed ? "quiet" : "primary"}
        >
          {item.subscribed ? <BellOff aria-hidden="true" size={14} /> : <Bell aria-hidden="true" size={14} />}
          {subscription.isPending
            ? "Updating…"
            : item.subscribed
              ? "Disable observation alert"
              : "Alert on next observation"}
        </Button>
        {subscription.isError && <span className="condition-inspector__action-error">{subscription.error.message}</span>}
      </footer>
    </section>
  );
}

export function ConditionScannerPage() {
  const workspaces = useConditionScannerWorkspaces();
  const workspace = workspaces.data?.[0];
  const [conditionKey, setConditionKey] = useState<ConditionKey>("trend_alignment");
  const [capTier, setCapTier] = useState<CapFilter>("all");
  const [observationFilter, setObservationFilter] = useState<ObservationFilter>("all");
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const scan = useConditionScan(workspace?.id, {
    conditionKey,
    capTier,
    newOnly: observationFilter === "new",
    limit: 150,
  });
  const capOptions = useMemo<readonly SelectOption<CapFilter>[]>(() => [
    { value: "all", label: "All capitalization tiers" },
    ...researchDeployment.capTiers.map((tier) => ({
      value: tier,
      label: CAP_LABELS[tier] ?? tier,
    })),
  ], []);
  const selected = scan.data?.items.find((item) => item.ticker === selectedTicker)
    ?? scan.data?.items[0]
    ?? null;

  useEffect(() => {
    if (selected?.ticker !== selectedTicker) setSelectedTicker(selected?.ticker ?? null);
  }, [selected?.ticker, selectedTicker]);

  if (workspaces.isLoading || (workspace && scan.isLoading)) {
    return <div aria-label="Loading condition scanner" className="research-loading"><span className="research-loading__header" /><span className="research-loading__summary" /><span className="research-loading__body" /></div>;
  }

  if (workspaces.isError || scan.isError) {
    return (
      <section className="research-unavailable">
        <CircleAlert aria-hidden="true" size={26} />
        <h1>Condition evidence unavailable</h1>
        <p>{workspaces.error?.message ?? scan.error?.message ?? "The tenant-bound completed-session scan could not be loaded."}</p>
        <Button onPress={() => void (workspaces.isError ? workspaces.refetch() : scan.refetch())} variant="secondary"><RefreshCw aria-hidden="true" size={14} /> Retry</Button>
      </section>
    );
  }

  if (!workspace || !scan.data) {
    return (
      <section className="research-unavailable">
        <CircleAlert aria-hidden="true" size={26} />
        <h1>Research workspace unavailable</h1>
        <p>No {researchDeployment.exchangeName} workspace was provisioned for this account.</p>
      </section>
    );
  }

  return (
    <div className="condition-scanner-page">
      <header className="condition-page-header">
        <div>
          <span className="condition-page-header__eyebrow">Completed-session market evidence · {researchDeployment.exchangeName}</span>
          <h1>Condition scanner</h1>
          <p>Find securities that currently match a registered research definition, inspect every input, and measure historical follow-through without turning a screen into a trade recommendation.</p>
        </div>
        <StatusBadge tone={scan.data.latestSessionDate ? "positive" : "warning"} dot>
          {scan.data.latestSessionDate ? `Through ${dateLabel(scan.data.latestSessionDate)}` : "Awaiting session data"}
        </StatusBadge>
      </header>

      <section aria-label="Condition scanner controls" className="condition-controls">
        <div className="condition-controls__families">
          <SegmentedControl label="Research condition" onChange={setConditionKey} options={CONDITION_OPTIONS} value={conditionKey} />
        </div>
        <div className="condition-controls__filters">
          <SegmentedControl
            label="Observation state"
            onChange={setObservationFilter}
            options={[
              { value: "all", label: "All observed", count: scan.data.observedCount },
              { value: "new", label: "New this session", count: scan.data.newCount },
            ]}
            value={observationFilter}
          />
          <SelectField label="Capitalization tier" onChange={setCapTier} options={capOptions} value={capTier} />
        </div>
      </section>

      <section aria-label="Condition scan summary" className="condition-summary">
        <div><CalendarDays aria-hidden="true" size={15} /><span><small>Latest completed session</small><strong>{dateLabel(scan.data.latestSessionDate)}</strong></span></div>
        <div><Radar aria-hidden="true" size={15} /><span><small>Currently observed</small><strong>{scan.data.observedCount.toLocaleString()}</strong></span></div>
        <div><Activity aria-hidden="true" size={15} /><span><small>First observed this session</small><strong>{scan.data.newCount.toLocaleString()}</strong></span></div>
        <div><ShieldCheck aria-hidden="true" size={15} /><span><small>Methodology</small><strong>{scan.data.methodologyVersion}</strong></span></div>
      </section>

      <div className="condition-definition">
        <span><strong>{scan.data.definition.title}</strong><small>{scan.data.definition.category} · definition {scan.data.definition.version}</small></span>
        <p>{scan.data.definition.whyItMatters}</p>
        <StatusBadge tone="info">Research context</StatusBadge>
      </div>

      <CalibrationPanel scan={scan.data} />

      <section className="condition-workbench">
        <aside aria-label="Observed securities" className="condition-observation-list">
          <header>
            <span><strong>{scan.data.returnedCount.toLocaleString()} observations shown</strong><small>Most recent observation first, then trading capacity</small></span>
            {scan.isFetching && <RefreshCw aria-label="Refreshing observations" className="condition-spin" size={14} />}
          </header>
          <div className="condition-observation-list__rows">
            {scan.data.items.map((item) => (
              <ObservationRow key={item.ticker} item={item} onSelect={() => setSelectedTicker(item.ticker)} selected={selected?.ticker === item.ticker} />
            ))}
            {!scan.data.items.length && <div className="condition-observation-list__empty"><Radar aria-hidden="true" size={22} /><strong>No matching observation</strong><small>Try all observations or a broader capitalization tier.</small></div>}
          </div>
        </aside>
        <ConditionInspector item={selected} scan={scan.data} workspaceId={workspace.id} />
      </section>

      <section aria-label="Methodology cautions" className="condition-warnings">
        {scan.data.warnings.map((warning) => <p key={warning}><CircleAlert aria-hidden="true" size={13} />{warning}</p>)}
      </section>
    </div>
  );
}
