import {
  Ban,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Gauge,
  ShieldAlert,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import {
  researchApi,
  type SqueezeEntry,
  type SqueezeFamily,
  type SqueezeState,
} from "../../app/api-client";
import { isResearchPreview, researchDeployment } from "../../app/deployment";
import {
  IconButton,
  SegmentedControl,
  SelectField,
  StatusBadge,
  type StatusTone,
} from "../../design-system";
import { previewSqueezeMonitor } from "./preview-data";

const STATE_LABEL: Record<SqueezeState, string> = {
  watch: "Watch",
  forming: "Forming",
  trigger_ready: "Trigger ready",
  confirmed: "Confirmed",
  exhausted: "Too extended",
  failed: "Failed",
};

const STATE_TONE: Record<SqueezeState, StatusTone> = {
  watch: "neutral",
  forming: "warning",
  trigger_ready: "warning",
  confirmed: "positive",
  exhausted: "negative",
  failed: "negative",
};

/** Humanize a persisted state key: the archive stores snake_case, users read prose. */
function stateLabel(state: string): string {
  return STATE_LABEL[state as SqueezeState] ?? state.replace(/_/g, " ");
}

type StateFilter = "all" | "actionable" | "confirmed" | "late";

function matchesState(entry: SqueezeEntry, filter: StateFilter): boolean {
  if (filter === "actionable") {
    return entry.state === "forming" || entry.state === "trigger_ready";
  }
  if (filter === "confirmed") return entry.state === "confirmed";
  if (filter === "late") return entry.state === "exhausted" || entry.state === "failed";
  return true;
}

function signed(value: number | null): string {
  if (value === null) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function price(value: number | null): string {
  if (value === null) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: researchDeployment.currency,
    maximumFractionDigits: value < 10 ? 3 : 2,
  }).format(value);
}

export function SqueezeMonitorPanel() {
  const [asOf, setAsOf] = useState<string>();
  const [familyKey, setFamilyKey] = useState<string>();
  const [stateFilter, setStateFilter] = useState<StateFilter>("all");
  const [capTier, setCapTier] = useState("all");
  const [selectedId, setSelectedId] = useState<string>();
  const monitor = useQuery({
    queryKey: ["research", "squeeze-monitor", asOf ?? "latest"],
    queryFn: () =>
      isResearchPreview
        ? Promise.resolve(previewSqueezeMonitor)
        : researchApi.squeezeMonitor(asOf),
    refetchInterval: asOf ? false : 60_000,
  });

  const families = monitor.data?.families ?? [];
  const activeFamily: SqueezeFamily | undefined =
    families.find((family) => family.family === familyKey) ??
    families.find((family) => family.status === "available");
  const familyEntries = activeFamily?.entries ?? [];
  const entries = useMemo(
    () =>
      familyEntries.filter(
        (entry) =>
          matchesState(entry, stateFilter) &&
          (capTier === "all" || entry.capTier === capTier),
      ),
    [familyEntries, stateFilter, capTier],
  );

  useEffect(() => {
    const id = (entry: SqueezeEntry) => `${entry.family}:${entry.code}`;
    if (entries.some((entry) => id(entry) === selectedId)) return;
    setSelectedId(entries[0] ? id(entries[0]) : undefined);
  }, [entries, selectedId]);

  if (monitor.isLoading || monitor.isError || !monitor.data) return null;
  const data = monitor.data;
  const selected =
    entries.find((entry) => `${entry.family}:${entry.code}` === selectedId) ?? entries[0];
  const dates = data.availableDates;
  const selectedDate = data.selectedDate ?? "";
  const dateIndex = dates.indexOf(selectedDate);
  const chooseDate = (value: string) => {
    setAsOf(value === data.latestDate ? undefined : value);
    setSelectedId(undefined);
  };
  const capOptions = [
    { value: "all", label: "All capitalization tiers" },
    ...researchDeployment.capTiers.map((tier) => ({
      value: tier,
      label: `${tier.charAt(0).toUpperCase()}${tier.slice(1)} cap`,
    })),
  ];

  return (
    <section className="atlas-panel squeeze-monitor">
      <header className="squeeze-monitor__header">
        <span>
          <strong>Squeeze monitor</strong>
          <small>
            Deterministic setup taxonomy (squeeze-monitor-v1). Families without their required
            datasets are shown blocked — absence is an answer, not a gap.
          </small>
        </span>
        <div className="squeeze-monitor__date">
          <IconButton
            isDisabled={dateIndex < 0 || dateIndex >= dates.length - 1}
            label="Previous archived session"
            onPress={() => chooseDate(dates[dateIndex + 1]!)}
          >
            <ChevronLeft aria-hidden="true" size={15} />
          </IconButton>
          {dates.length > 0 ? (
            <SelectField
              label="Archived scan date"
              onChange={chooseDate}
              options={dates.map((date) => ({
                value: date,
                label: date === data.latestDate ? `${date} · latest` : date,
              }))}
              value={selectedDate}
            />
          ) : (
            <span className="squeeze-monitor__no-date">No archived scans yet</span>
          )}
          <IconButton
            isDisabled={dateIndex <= 0}
            label="Next archived session"
            onPress={() => chooseDate(dates[dateIndex - 1]!)}
          >
            <ChevronRight aria-hidden="true" size={15} />
          </IconButton>
        </div>
      </header>

      <div className="squeeze-monitor__families" role="tablist">
        {families.map((family) => (
          <button
            aria-selected={family.family === activeFamily?.family}
            className={family.status === "data_blocked" ? "is-blocked" : undefined}
            key={family.family}
            onClick={() => {
              setFamilyKey(family.family);
              setSelectedId(undefined);
            }}
            role="tab"
            type="button"
          >
            {family.status === "data_blocked" && <Ban aria-hidden="true" size={12} />}
            {family.label}
            {family.status === "available" && <em>{family.entries.length}</em>}
          </button>
        ))}
      </div>

      {activeFamily?.status === "data_blocked" ? (
        <div className="squeeze-monitor__blocked">
          <Ban aria-hidden="true" size={18} />
          <div>
            <strong>{activeFamily.label} is data-blocked</strong>
            <p>{activeFamily.blockedReason}</p>
            <ul>
              {activeFamily.missingDatasets.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        </div>
      ) : (
        <>
          <div className="squeeze-monitor__toolbar">
            <SegmentedControl
              label="Setup states"
              onChange={setStateFilter}
              options={[
                { value: "all", label: "All", count: familyEntries.length },
                {
                  value: "actionable",
                  label: "Forming",
                  count: familyEntries.filter((entry) => matchesState(entry, "actionable")).length,
                },
                {
                  value: "confirmed",
                  label: "Confirmed",
                  count: familyEntries.filter((entry) => entry.state === "confirmed").length,
                },
                {
                  value: "late",
                  label: "Late/failed",
                  count: familyEntries.filter((entry) => matchesState(entry, "late")).length,
                },
              ]}
              value={stateFilter}
            />
            <SelectField
              label="Capitalization tier"
              onChange={setCapTier}
              options={capOptions}
              value={capTier}
            />
            <span>
              <CalendarDays aria-hidden="true" size={13} />
              Scan {data.selectedDate ?? "unavailable"}
            </span>
          </div>

          {entries.length === 0 ? (
            <div className="squeeze-monitor__empty">
              <Gauge aria-hidden="true" size={22} />
              <span>
                <strong>No archived setup in this view</strong>
                <small>
                  A ticker appears only when the deterministic taxonomy finds a measurable
                  condition. Silence is a valid answer.
                </small>
              </span>
            </div>
          ) : (
            <div className="squeeze-monitor__layout">
              <div className="squeeze-monitor__column">
                <p className="squeeze-monitor__count">
                  {entries.length} {entries.length === 1 ? "setup" : "setups"}
                  {entries.length > 8 ? " · strongest state first, scroll for more" : ""}
                </p>
                <div className="squeeze-monitor__list" role="list">
                {entries.map((entry) => (
                  <button
                    aria-current={
                      `${entry.family}:${entry.code}` ===
                      (selected ? `${selected.family}:${selected.code}` : undefined)
                        ? "true"
                        : undefined
                    }
                    key={`${entry.family}:${entry.code}`}
                    onClick={() => setSelectedId(`${entry.family}:${entry.code}`)}
                    role="listitem"
                    type="button"
                  >
                    <span className="squeeze-monitor__identity">
                      <strong>${entry.code}</strong>
                      {entry.isNew && <em>New</em>}
                    </span>
                    <StatusBadge tone={STATE_TONE[entry.state]}>
                      {STATE_LABEL[entry.state]}
                    </StatusBadge>
                    <small className="squeeze-monitor__meta">
                      {entry.capTier} cap · {entry.sessionsSinceDiscovery}{" "}
                      {entry.sessionsSinceDiscovery === 1 ? "session" : "sessions"}
                    </small>
                    <span className="squeeze-monitor__return">
                      <b
                        className={
                          (entry.returnSinceDiscoveryPct ?? 0) >= 0 ? "value-up" : "value-down"
                        }
                      >
                        {signed(entry.returnSinceDiscoveryPct)}
                      </b>
                    </span>
                  </button>
                ))}
                </div>
              </div>

              {selected && (
                <article className="squeeze-monitor__detail">
                  <header>
                    <span>
                      <small>{selected.familyLabel}</small>
                      <h3>${selected.code}</h3>
                      <p>{selected.company}</p>
                    </span>
                    <StatusBadge dot tone={STATE_TONE[selected.state]}>
                      {STATE_LABEL[selected.state]}
                    </StatusBadge>
                  </header>
                  <div className="squeeze-monitor__metrics">
                    <span><small>First discovery</small><strong>{selected.firstDiscoveredOn}</strong><em>{price(selected.discoveryPrice)}</em></span>
                    <span><small>As-of price</small><strong>{price(selected.asOfPrice)}</strong><em>{selected.asOfDate}</em></span>
                    <span><small>Best / worst path</small><strong>{signed(selected.maxFavorablePct)} / {signed(selected.maxAdversePct)}</strong><em>MFE / MAE</em></span>
                    <span><small>Trigger</small><strong>{price(selected.triggerPrice)}</strong><em>base high</em></span>
                    <span><small>Invalidation</small><strong>{price(selected.invalidationPrice)}</strong><em>{selected.riskPerShare !== null ? `${selected.riskPerShare.toFixed(2)} risk/share` : "—"}</em></span>
                    <span><small>Planning objective</small><strong>{price(selected.planningObjectivePrice)}</strong><em>{selected.planningRewardRisk !== null ? `${selected.planningRewardRisk.toFixed(1)}R · not a forecast` : "not applicable"}</em></span>
                  </div>
                  <p className="squeeze-monitor__reason">
                    <strong>
                      {selected.previousState &&
                      selected.previousState !== "none" &&
                      selected.previousState !== selected.state
                        ? `${stateLabel(selected.previousState)} → ${stateLabel(selected.state)}. `
                        : ""}
                    </strong>
                    {selected.stateReason}
                  </p>
                  <span className="squeeze-monitor__holding">
                    <Clock3 aria-hidden="true" size={12} />{selected.expectedHolding} · {selected.liquidityCapacityNote}
                  </span>
                  {selected.supportingEvidence.length > 0 && (
                    <div className="squeeze-monitor__evidence">
                      <strong>Supporting</strong>
                      <ul>{selected.supportingEvidence.map((item) => <li key={item}>{item}</li>)}</ul>
                    </div>
                  )}
                  {selected.counterEvidence.length > 0 && (
                    <div className="squeeze-monitor__evidence squeeze-monitor__evidence--counter">
                      <strong>Counter-evidence</strong>
                      <ul>{selected.counterEvidence.map((item) => <li key={item}>{item}</li>)}</ul>
                    </div>
                  )}
                  {[...selected.dataQuality, ...selected.missingEvidence].map((note) => (
                    <span className="squeeze-monitor__note" key={note}>
                      <ShieldAlert aria-hidden="true" size={12} />{note}
                    </span>
                  ))}
                  <span className="squeeze-monitor__note">
                    <ShieldAlert aria-hidden="true" size={12} />{selected.paperBookStatus}
                  </span>
                </article>
              )}
            </div>
          )}
        </>
      )}

      <details className="squeeze-monitor__limits">
        <summary>Methodology and hard limitations</summary>
        <p>{data.methodology}</p>
        <ul>
          {data.limitations.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </details>
    </section>
  );
}
