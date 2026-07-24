import {
  ArrowRight,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  CircleOff,
  Clock3,
  Crosshair,
  DatabaseZap,
  ShieldAlert,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { researchDeployment } from "../../app/deployment";
import type { DecisionCandidateState } from "../../app/api-client";
import {
  Button,
  IconButton,
  SegmentedControl,
  SelectField,
  StatusBadge,
  type StatusTone,
} from "../../design-system";
import { DecisionPathChart } from "./DecisionPathChart";
import {
  decisionStateLabel,
  matchesCapTier,
  matchesDecisionFilter,
  type DecisionBoardFilter,
} from "./decision-board";
import { useDecisionBoard, useDecisionCandidatePath } from "./hooks";

function stateTone(state: DecisionCandidateState): StatusTone {
  if (state === "ready") return "warning";
  if (state === "manage") return "positive";
  if (state === "exit" || state === "blocked") return "negative";
  return "neutral";
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

function CandidateIcon({ state }: { state: DecisionCandidateState }) {
  if (state === "ready") return <Crosshair aria-hidden="true" size={16} />;
  if (state === "manage") return <TrendingUp aria-hidden="true" size={16} />;
  if (state === "exit") return <TrendingDown aria-hidden="true" size={16} />;
  if (state === "blocked") return <ShieldAlert aria-hidden="true" size={16} />;
  return <CircleOff aria-hidden="true" size={16} />;
}

export function DecisionBoardPanel({ workspaceId }: { workspaceId: string }) {
  const navigate = useNavigate();
  const [asOf, setAsOf] = useState<string>();
  const [filter, setFilter] = useState<DecisionBoardFilter>("all");
  const [capTier, setCapTier] = useState("all");
  const [selectedId, setSelectedId] = useState<string>();
  const board = useDecisionBoard(workspaceId, asOf);
  const capCandidates = useMemo(
    () => (board.data?.candidates ?? []).filter(
      (candidate) => matchesCapTier(candidate, capTier),
    ),
    [board.data?.candidates, capTier],
  );
  const candidates = useMemo(
    () => capCandidates.filter(
      (candidate) => matchesDecisionFilter(candidate, filter),
    ),
    [capCandidates, filter],
  );

  useEffect(() => {
    if (candidates.some((candidate) => candidate.id === selectedId)) return;
    setSelectedId(candidates[0]?.id);
  }, [candidates, selectedId]);

  const selected = candidates.find((candidate) => candidate.id === selectedId) ?? candidates[0];
  const path = useDecisionCandidatePath(
    workspaceId,
    selected?.portfolioId,
    selected?.code,
    board.data?.selectedDate ?? asOf,
  );
  const dates = board.data?.availableDates ?? [];
  const selectedDate = board.data?.selectedDate ?? "";
  const dateIndex = dates.indexOf(selectedDate);
  const chooseDate = (value: string) => {
    setAsOf(value === board.data?.latestDate ? undefined : value);
    setSelectedId(undefined);
  };
  const filterOptions = [
    { value: "all", label: "All", count: capCandidates.length },
    {
      value: "entries",
      label: "Entries",
      count: capCandidates.filter(
        (candidate) => candidate.state === "ready" || candidate.state === "blocked",
      ).length ?? 0,
    },
    {
      value: "positions",
      label: "Positions",
      count: capCandidates.filter((candidate) => candidate.state === "manage").length,
    },
    {
      value: "exits",
      label: "Exits",
      count: capCandidates.filter(
        (candidate) => candidate.state === "exit" || candidate.state === "closed",
      ).length ?? 0,
    },
  ] as const;
  const capOptions = [
    { value: "all", label: "All capitalization tiers" },
    ...researchDeployment.capTiers.map((tier) => ({
      value: tier,
      label: `${tier.charAt(0).toUpperCase()}${tier.slice(1)} cap`,
    })),
  ];
  const shortCapability = board.data?.directionCapabilities.find(
    (capability) => capability.direction === "short",
  );

  return (
    <section className="atlas-panel decision-board">
      <header className="decision-board__header">
        <span>
          <strong>Agent decisions</strong>
          <small>Registered strategy targets, paper positions and measured follow-through</small>
        </span>
        <div className="decision-board__date">
          <IconButton
            isDisabled={dateIndex < 0 || dateIndex >= dates.length - 1}
            label="Previous completed session"
            onPress={() => chooseDate(dates[dateIndex + 1]!)}
          >
            <ChevronLeft aria-hidden="true" size={15} />
          </IconButton>
          {dates.length > 0 ? (
            <SelectField
              label="Archived decision date"
              onChange={chooseDate}
              options={dates.map((date) => ({
                value: date,
                label: date === board.data?.latestDate ? `${date} · latest` : date,
              }))}
              value={selectedDate}
            />
          ) : (
            <span className="decision-board__no-date">No snapshots</span>
          )}
          <IconButton
            isDisabled={dateIndex <= 0}
            label="Next completed session"
            onPress={() => chooseDate(dates[dateIndex - 1]!)}
          >
            <ChevronRight aria-hidden="true" size={15} />
          </IconButton>
        </div>
      </header>

      {board.isLoading ? (
        <div className="decision-board__loading" aria-label="Loading agent decisions">
          <span /><span /><span />
        </div>
      ) : board.isError ? (
        <div className="decision-board__unavailable">
          <DatabaseZap aria-hidden="true" size={20} />
          <span><strong>Decision archive unavailable</strong><small>{board.error.message}</small></span>
          <Button onPress={() => board.refetch()} variant="quiet">Retry</Button>
        </div>
      ) : (
        <>
          <div className="decision-board__toolbar">
            <div className="decision-board__filters">
              <SegmentedControl
                label="Decision states"
                onChange={setFilter}
                options={filterOptions}
                value={filter}
              />
              <SelectField
                label="Capitalization tier"
                onChange={setCapTier}
                options={capOptions}
                value={capTier}
              />
            </div>
            <span>
              <CalendarDays aria-hidden="true" size={13} />
              Snapshot {board.data?.selectedDate ?? "unavailable"}
              {board.data?.selectedDate !== board.data?.latestDate && <b>Archived</b>}
            </span>
          </div>
          {researchDeployment.market === "US" && shortCapability?.status === "blocked" && (
            <div className="decision-board__direction-note">
              <ShieldAlert aria-hidden="true" size={14} />
              <span>
                <strong>Long book active · short book data-blocked</strong>
                <small>{shortCapability.reason}</small>
              </span>
            </div>
          )}

          {candidates.length === 0 ? (
            <div className="decision-board__empty">
              <Clock3 aria-hidden="true" size={22} />
              <span>
                <strong>No agent decision in this view</strong>
                <small>
                  Atlas does not promote research urgency into a trade. A registered paper strategy
                  must form a target before a ticker appears here.
                </small>
              </span>
            </div>
          ) : (
            <div className="decision-board__layout">
              <div className="decision-board__list" role="list">
                {candidates.map((candidate) => (
                  <button
                    aria-current={candidate.id === selected?.id ? "true" : undefined}
                    key={candidate.id}
                    onClick={() => setSelectedId(candidate.id)}
                    role="listitem"
                    type="button"
                  >
                    <span className={`decision-board__state-icon decision-board__state-icon--${candidate.state}`}>
                      <CandidateIcon state={candidate.state} />
                    </span>
                    <span className="decision-board__identity">
                      <span>
                        <strong>${candidate.code}</strong>
                        {candidate.isNew && <em>New</em>}
                      </span>
                      <small>{candidate.horizon} · {candidate.strategyName}</small>
                    </span>
                    <span className="decision-board__return">
                      <strong className={(candidate.returnSinceDiscoveryPct ?? 0) >= 0 ? "value-up" : "value-down"}>
                        {signed(candidate.returnSinceDiscoveryPct)}
                      </strong>
                      <small>since {candidate.firstDiscoveredOn}</small>
                    </span>
                    <StatusBadge tone={stateTone(candidate.state)}>
                      {decisionStateLabel(candidate.state)}
                    </StatusBadge>
                  </button>
                ))}
              </div>

              {selected && (
                <article className="decision-board__detail">
                  <header>
                    <span>
                      <small>{selected.horizon} decision · {selected.portfolioName}</small>
                      <h2>${selected.code}</h2>
                      <p>{selected.company}</p>
                    </span>
                      <StatusBadge dot tone={stateTone(selected.state)}>
                        {decisionStateLabel(selected.state)}
                      </StatusBadge>
                  </header>
                  <div className="decision-board__metrics">
                    <span><small>First discovery</small><strong>{selected.firstDiscoveredOn}</strong><em>{price(selected.discoveryPrice)}</em></span>
                    <span><small>As-of price</small><strong>{price(selected.asOfPrice)}</strong><em>{selected.sessionsSinceDiscovery} sessions</em></span>
                    <span><small>Follow-through</small><strong className={(selected.returnSinceDiscoveryPct ?? 0) >= 0 ? "value-up" : "value-down"}>{signed(selected.returnSinceDiscoveryPct)}</strong><em>not paper P&amp;L</em></span>
                    <span><small>Best / worst path</small><strong>{signed(selected.maxFavorablePct)} / {signed(selected.maxAdversePct)}</strong><em>MFE / MAE</em></span>
                    <span><small>Next target</small><strong>{selected.targetWeightPct.toFixed(1)}%</strong><em>portfolio weight</em></span>
                    <span><small>Risk invalidation</small><strong>{price(selected.invalidationPrice)}</strong><em>{selected.riskReferencePrice === null ? "no active entry plan" : `from ${price(selected.riskReferencePrice)}`}</em></span>
                    <span><small>Planning objective</small><strong>{price(selected.planningObjectivePrice)}</strong><em>{selected.planningRewardRisk === null ? "not applicable" : `${selected.planningRewardRisk.toFixed(1)}R · not a forecast`}</em></span>
                  </div>
                  <div className="decision-board__story">
                    <strong>{selected.headline}</strong>
                    <span className="decision-board__holding">
                      <Clock3 aria-hidden="true" size={12} />{selected.expectedHolding}
                    </span>
                    <span className="decision-board__classification">
                      {selected.direction.toUpperCase()} · {selected.capTier.replace("_", " ")} cap ·{" "}
                      {selected.evidenceMode === "forward" ? "forward paper evidence" : "historical replay"}
                    </span>
                    <p>{selected.story}</p>
                    <span><ShieldAlert aria-hidden="true" size={12} />{selected.exitPolicy}</span>
                    {selected.riskNotes.map((note) => (
                      <span key={note}><ShieldAlert aria-hidden="true" size={12} />{note}</span>
                    ))}
                  </div>
                  {path.isLoading ? (
                    <div className="decision-board__chart-loading" aria-label="Loading decision path" />
                  ) : path.data ? (
                    <>
                      <DecisionPathChart path={path.data} />
                      <p className="decision-board__basis">{path.data.priceBasis}</p>
                    </>
                  ) : (
                    <p className="decision-board__basis">The completed price path is unavailable.</p>
                  )}
                  <Button
                    onPress={() => navigate(`/companies/${encodeURIComponent(selected.code)}`)}
                    variant="quiet"
                  >
                    Open company research <ArrowRight aria-hidden="true" size={14} />
                  </Button>
                </article>
              )}
            </div>
          )}
          <p className="decision-board__method">{board.data?.methodology}</p>
        </>
      )}
    </section>
  );
}
