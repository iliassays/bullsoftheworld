import {
  Ban,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Clock3,
  DatabaseZap,
  Gauge,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import {
  researchApi,
  type SqueezeEntry,
  type SqueezeFamily,
} from "../../app/api-client";
import { isResearchPreview, researchDeployment } from "../../app/deployment";
import {
  Button,
  IconButton,
  SegmentedControl,
  SelectField,
  StatusBadge,
} from "../../design-system";
import { SqueezeChart } from "./SqueezeChart";
import { SqueezeLifecycle } from "./SqueezeLifecycle";
import { previewSqueezeMonitor, previewSqueezePath } from "./preview-data";
import {
  SQUEEZE_STATE_LABEL,
  SQUEEZE_STATE_EXPLANATION,
  SQUEEZE_STATE_TONE,
  squeezeReferenceCopy,
  squeezeStateLabel,
} from "./squeeze-state";

type StateFilter = "new" | "developing" | "confirmed" | "late" | "all";

function matchesState(entry: SqueezeEntry, filter: StateFilter): boolean {
  if (filter === "new") return entry.isNew || entry.isNewConfirmation;
  if (filter === "developing") {
    return (
      entry.state === "watch" ||
      entry.state === "forming" ||
      entry.state === "trigger_ready"
    );
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
  const [stateFilter, setStateFilter] = useState<StateFilter>("new");
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
  const defaultFamily =
    families.find(
      (family) =>
        family.status === "available" &&
        family.entries.some((entry) => entry.isNew || entry.isNewConfirmation),
    ) ?? families.find((family) => family.status === "available");
  const activeFamily: SqueezeFamily | undefined =
    families.find((family) => family.family === familyKey) ??
    defaultFamily;
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

  // Resolved before the early return below: hooks may not run conditionally.
  const selected =
    entries.find((entry) => `${entry.family}:${entry.code}` === selectedId) ?? entries[0];
  const archiveDate = monitor.data?.selectedDate ?? undefined;
  const path = useQuery({
    queryKey: [
      "research",
      "squeeze-path",
      selected?.family,
      selected?.code,
      archiveDate ?? "latest",
    ],
    queryFn: () =>
      isResearchPreview
        ? Promise.resolve(previewSqueezePath(selected!.family, selected!.code))
        : researchApi.squeezePath(selected!.family, selected!.code, archiveDate),
    enabled: Boolean(selected),
  });

  if (monitor.isLoading) {
    return (
      <section className="atlas-panel squeeze-monitor">
        <header className="squeeze-monitor__header">
          <span>
            <strong>Squeeze monitor</strong>
            <small>Loading the tenant-bound setup archive.</small>
          </span>
          <span className="squeeze-monitor__no-date">Loading archive</span>
        </header>
        <div className="squeeze-monitor__loading" aria-label="Loading squeeze monitor">
          <span /><span /><span />
        </div>
      </section>
    );
  }

  if (monitor.isError || !monitor.data) {
    const detail =
      monitor.error instanceof Error
        ? monitor.error.message
        : "The tenant-bound squeeze archive did not return a usable response.";
    return (
      <section className="atlas-panel squeeze-monitor">
        <header className="squeeze-monitor__header">
          <span>
            <strong>Squeeze monitor</strong>
            <small>
              Deterministic setup taxonomy. Missing data is shown explicitly, never hidden.
            </small>
          </span>
          <span className="squeeze-monitor__no-date">Archive unavailable</span>
        </header>
        <div className="squeeze-monitor__unavailable" role="alert">
          <DatabaseZap aria-hidden="true" size={20} />
          <span>
            <strong>Squeeze monitor unavailable</strong>
            <small>{detail}</small>
          </span>
          <Button onPress={() => monitor.refetch()} variant="quiet">
            <RefreshCw aria-hidden="true" size={14} />
            Retry
          </Button>
        </div>
      </section>
    );
  }

  const data = monitor.data;
  const dates = data.availableDates;
  const selectedDate = data.selectedDate ?? "";
  const dateIndex = dates.indexOf(selectedDate);
  const chooseDate = (value: string) => {
    setAsOf(value === data.latestDate ? undefined : value);
    setFamilyKey(undefined);
    setStateFilter("new");
    setSelectedId(undefined);
  };
  const openLifecycleSnapshot = (date: string, entry: SqueezeEntry) => {
    setAsOf(date === data.latestDate ? undefined : date);
    setFamilyKey(entry.family);
    setStateFilter("all");
    setCapTier("all");
    setSelectedId(`${entry.family}:${entry.code}`);
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
            Research taxonomy, not a trade queue. Current engine: {data.methodologyVersion};
            archived rows retain their original method.
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

      <div className="squeeze-monitor__execution-boundary">
        <ShieldAlert aria-hidden="true" size={15} />
        <span>
          <strong>Research scan only. No order is created from this list.</strong>
          “Rule confirmed” means the setup conditions completed, not high probability. Most rows
          will never qualify. Only a separate, evidence-admitted and risk-sized strategy can
          create a paper target shown in Agent decisions.
        </span>
      </div>

      <div className="squeeze-monitor__reading-key" aria-label="How to read setup states">
        <span>
          <small>Setup stage</small>
          <strong>Early watch → Base forming → Near trigger → Rule confirmed</strong>
          <em>Failed and Too extended close the active setup.</em>
        </span>
        <span>
          <small>Outcome clock</small>
          <strong>Measured only after a later completed session exists</strong>
          <em>A rule can be confirmed while its later outcome is still not measurable.</em>
        </span>
      </div>

      <div className="squeeze-monitor__families" role="tablist">
        {families.map((family) => {
          const newCount = family.entries.filter(
            (entry) => entry.isNew || entry.isNewConfirmation,
          ).length;
          return (
            <button
              aria-selected={family.family === activeFamily?.family}
              className={family.status !== "available" ? "is-blocked" : undefined}
              key={family.family}
              onClick={() => {
                setFamilyKey(family.family);
                setSelectedId(undefined);
              }}
              role="tab"
              type="button"
            >
              {family.status !== "available" && <Ban aria-hidden="true" size={12} />}
              {family.label}
              {family.status === "available" && (
                <em>{newCount > 0 ? `${newCount} new` : family.entries.length}</em>
              )}
            </button>
          );
        })}
      </div>

      {activeFamily && activeFamily.status !== "available" ? (
        <div className="squeeze-monitor__blocked">
          <Ban aria-hidden="true" size={18} />
          <div>
            <strong>
              {activeFamily.label}{" "}
              {activeFamily.status === "data_blocked"
                ? "is data-blocked"
                : "has its data but no strategy yet"}
            </strong>
            <p>{activeFamily.blockedReason}</p>
            <ul>
              {activeFamily.missingDatasets.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            {activeFamily.status === "not_implemented" && (
              <p>
                Short execution stays blocked regardless: identifying a setup and being able to
                borrow, locate and carry a short are different requirements.
              </p>
            )}
          </div>
        </div>
      ) : (
        <>
          <div className="squeeze-monitor__toolbar">
            <SegmentedControl
              label="Setup states"
              onChange={setStateFilter}
              options={[
                {
                  value: "new",
                  label: "Changed this scan",
                  count: familyEntries.filter((entry) => matchesState(entry, "new")).length,
                },
                {
                  value: "developing",
                  label: "Developing",
                  count: familyEntries.filter((entry) => matchesState(entry, "developing")).length,
                },
                {
                  value: "confirmed",
                  label: "Rule confirmed",
                  count: familyEntries.filter((entry) => entry.state === "confirmed").length,
                },
                {
                  value: "late",
                  label: "Late/failed",
                  count: familyEntries.filter((entry) => matchesState(entry, "late")).length,
                },
                { value: "all", label: "All", count: familyEntries.length },
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
                  {stateFilter === "new"
                    ? "No setup was first discovered or first confirmed on this archived date."
                    : "No setup matches this state and capitalization filter."}
                </small>
              </span>
            </div>
          ) : (
            <div className="squeeze-monitor__layout">
              <div className="squeeze-monitor__column">
                <p className="squeeze-monitor__count">
                  {entries.length}{" "}
                  {stateFilter === "new"
                    ? entries.length === 1
                      ? "new transition"
                      : "new transitions"
                    : entries.length === 1
                      ? "setup"
                      : "setups"}
                  {entries.length > 8 ? " · newest transitions first, scroll for more" : ""}
                </p>
                <div className="squeeze-monitor__list" role="list">
                {entries.map((entry) => {
                  const hasObservableEntry = entry.returnSinceNextObservablePct !== null;
                  const displayedReturn = hasObservableEntry
                    ? entry.returnSinceNextObservablePct
                    : entry.returnSinceDiscoveryPct;
                  return (
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
                        {entry.isNewConfirmation ? (
                          <em className="squeeze-monitor__new-confirmation">Confirmed this scan</em>
                        ) : (
                          entry.isNew && <em>First seen this scan</em>
                        )}
                        {entry.evidenceMode === "reconstructed" && (
                          <em className="squeeze-monitor__replay" title="Reconstructed from stored bars, not collected on this session">
                            Replay
                          </em>
                        )}
                      </span>
                      <StatusBadge tone={SQUEEZE_STATE_TONE[entry.state]}>
                        {SQUEEZE_STATE_LABEL[entry.state]}
                      </StatusBadge>
                      <small className="squeeze-monitor__meta">
                        {entry.capTier} cap · {entry.sessionsSinceDiscovery}{" "}
                        completed {entry.sessionsSinceDiscovery === 1 ? "session" : "sessions"} since first seen
                      </small>
                      <span className="squeeze-monitor__return">
                        <b
                          className={
                            displayedReturn === null
                              ? undefined
                              : displayedReturn >= 0
                                ? "value-up"
                                : "value-down"
                          }
                        >
                          {displayedReturn === null ? "Not measured" : signed(displayedReturn)}
                        </b>
                        <small>
                          {displayedReturn === null
                            ? "No later close in this snapshot"
                            : hasObservableEntry
                              ? "after confirmation"
                              : "from discovery"}
                        </small>
                      </span>
                    </button>
                  );
                })}
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
                    <StatusBadge dot tone={SQUEEZE_STATE_TONE[selected.state]}>
                      {SQUEEZE_STATE_LABEL[selected.state]}
                    </StatusBadge>
                  </header>
                  <p className="squeeze-monitor__state-explanation">
                    <strong>Current setup stage:</strong>{" "}
                    {SQUEEZE_STATE_EXPLANATION[selected.state]}
                  </p>
                  {selected.methodologyVersion !== data.methodologyVersion && (
                    <p className="squeeze-monitor__method-warning">
                      <ShieldAlert aria-hidden="true" size={13} />
                      <span>
                        <strong>Legacy archived classification</strong>
                        This row used {selected.methodologyVersion}; the current engine is{" "}
                        {data.methodologyVersion}. It is preserved as point-in-time evidence and
                        has not been relabelled using today&apos;s rules.
                      </span>
                    </p>
                  )}
                  <div className="squeeze-monitor__timeline" aria-label="Setup evidence timeline">
                    <span>
                      <small>
                        {selected.firstConfirmedOn === selected.firstDiscoveredOn
                          ? "First observed"
                          : "Discovered"}
                      </small>
                      <strong>{selected.firstDiscoveredOn}</strong>
                      <em>{price(selected.discoveryPrice)}</em>
                    </span>
                    <span>
                      <small>First confirmed</small>
                      <strong>{selected.firstConfirmedOn ?? "Not reached"}</strong>
                      <em>
                        {selected.confirmationPrice !== null
                          ? selected.firstConfirmedOn === selected.firstDiscoveredOn
                            ? `${price(selected.confirmationPrice)} · same-session classification; no earlier phase recorded`
                            : `${price(selected.confirmationPrice)} · ${signed(selected.moveToConfirmationPct)} before confirmation`
                          : "condition, not an order"}
                      </em>
                    </span>
                    <span>
                      <small>Next observable open</small>
                      <strong>
                        {selected.nextObservableOn ?? "Not available in this snapshot"}
                      </strong>
                      <em>
                        {selected.nextObservablePrice === null
                          ? "Open a later archived session to observe it"
                          : price(selected.nextObservablePrice)}
                      </em>
                    </span>
                    <span>
                      <small>Gross follow-through</small>
                      <strong
                        className={
                          selected.returnSinceNextObservablePct === null
                            ? undefined
                            : selected.returnSinceNextObservablePct >= 0
                              ? "value-up"
                              : "value-down"
                        }
                      >
                        {selected.returnSinceNextObservablePct === null
                          ? "Not measured yet"
                          : signed(selected.returnSinceNextObservablePct)}
                      </strong>
                      <em>after confirmation · not P&amp;L</em>
                    </span>
                  </div>
                  <div className="squeeze-monitor__metrics">
                    <span>
                      <small>Discovery follow-through</small>
                      <strong>
                        {selected.returnSinceDiscoveryPct === null
                          ? "Not measured yet"
                          : signed(selected.returnSinceDiscoveryPct)}
                      </strong>
                      <em>
                        {selected.returnSinceDiscoveryPct === null
                          ? "this snapshot contains no later completed close"
                          : "pre-confirmation move included"}
                      </em>
                    </span>
                    <span>
                      <small>As-of price</small>
                      <strong>{price(selected.asOfPrice)}</strong>
                      <em>{selected.asOfDate}</em>
                    </span>
                    <span>
                      <small>Best / worst close</small>
                      <strong>
                        {selected.maxFavorablePct === null
                          ? "Not measured yet"
                          : `${signed(selected.maxFavorablePct)} / ${signed(selected.maxAdversePct)}`}
                      </strong>
                      <em>
                        {selected.maxFavorablePct === null
                          ? "this snapshot contains no later completed close"
                          : "MFE / MAE · close-to-close"}
                      </em>
                    </span>
                    {/* The close-based pair reports 0.00% adverse for setups that traded through
                        their own invalidation intraday (680 of 930 such rows on 2026-07-15), so
                        the traded extremes sit beside it. Excursions, not achievable returns. */}
                    <span title="Highest high and lowest low actually traded since discovery. An excursion, not a return you could have captured.">
                      <small>Peak / trough traded</small>
                      <strong>
                        {selected.peakTradedPct === null
                          ? "Not measured yet"
                          : `${signed(selected.peakTradedPct)} / ${signed(selected.troughTradedPct)}`}
                      </strong>
                      <em>
                        {selected.peakTradedPct === null
                          ? "this snapshot contains no later completed session"
                          : "post-discovery intraday high / low"}
                      </em>
                    </span>
                    <span>
                      <small>{squeezeReferenceCopy(selected).label}</small>
                      <strong>{price(selected.triggerPrice)}</strong>
                      <em>{squeezeReferenceCopy(selected).detail}</em>
                    </span>
                    <span><small>Invalidation</small><strong>{price(selected.invalidationPrice)}</strong><em>{selected.riskPerShare !== null ? `${selected.riskPerShare.toFixed(2)} risk/share` : "—"}</em></span>
                    <span><small>Planning objective</small><strong>{price(selected.planningObjectivePrice)}</strong><em>{selected.planningRewardRisk !== null ? `${selected.planningRewardRisk.toFixed(1)}R · not a forecast` : "not applicable"}</em></span>
                  </div>
                  <p className="squeeze-monitor__reason">
                    <strong>
                      {selected.previousState &&
                      selected.previousState !== "none" &&
                      selected.previousState !== selected.state
                        ? `${squeezeStateLabel(selected.previousState)} → ${squeezeStateLabel(selected.state)}. `
                        : ""}
                    </strong>
                    {selected.stateReason}
                  </p>
                  <span className="squeeze-monitor__holding">
                    <Clock3 aria-hidden="true" size={12} />{selected.expectedHolding} · Archive method {selected.methodologyVersion} · {selected.liquidityCapacityNote}
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
                  {selected.evidenceMode === "reconstructed" && (
                    <p className="squeeze-monitor__replay-note">
                      <ShieldAlert aria-hidden="true" size={12} />
                      Reconstructed from stored bars, not collected on this session. Only
                      currently-listed symbols exist in the store, so delisted names are absent and
                      the outcome shown is biased upward — a diagnostic, never forward performance.
                    </p>
                  )}
                  {path.isLoading ? (
                    <div className="squeeze-monitor__chart-loading" aria-label="Loading price history" />
                  ) : path.data && path.data.points.length > 1 ? (
                    <>
                      <SqueezeLifecycle
                        currency={researchDeployment.currency}
                        onSelectDate={(date) => openLifecycleSnapshot(date, selected)}
                        path={path.data}
                        selectedDate={selectedDate}
                        currentMethodologyVersion={data.methodologyVersion}
                      />
                      <SqueezeChart path={path.data} />
                    </>
                  ) : (
                    <p className="squeeze-monitor__note">
                      No completed price history is available to chart this setup.
                    </p>
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
