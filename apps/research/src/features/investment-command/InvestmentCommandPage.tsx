import {
  AlertTriangle,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpFromLine,
  BookOpenCheck,
  CalendarClock,
  CheckCircle2,
  CircleDollarSign,
  Clock3,
  DatabaseZap,
  Gauge,
  LineChart,
  RefreshCw,
  ShieldAlert,
  Target,
} from "lucide-react";
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";

import { researchDeployment } from "../../app/deployment";
import { Button, StatusBadge, type StatusTone } from "../../design-system";
import {
  useAutomationPolicy,
  useInvestmentOperatingView,
  useResearchRun,
  useResearchRuns,
  useShadowPortfolios,
} from "../autonomous-research/hooks";
import { eventTypeLabel, timingLabel } from "../catalyst-calendar/model";
import { useCatalystCalendar } from "../catalyst-calendar/useCatalystCalendar";
import { useResearchQueue, useResearchWorkspaces } from "../research-queue/useResearchQueue";
import {
  automationHeadline,
  buildDecisionActions,
  latestLifecycleRun,
  researchInbox,
  summarizeStrategyBooks,
  upcomingCatalysts,
  type DecisionAction,
} from "./model";

function dateTime(value: string | null | undefined): string {
  if (!value) return "Not available";
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(new Date(value));
}

function money(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: researchDeployment.currency,
    maximumFractionDigits: 0,
  }).format(value);
}

function signed(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function promotionTone(status: string): StatusTone {
  if (status === "eligible") return "positive";
  if (status === "rejected") return "negative";
  return "warning";
}

function actionIcon(action: DecisionAction) {
  if (action.kind === "risk") return <ShieldAlert aria-hidden="true" size={16} />;
  if (action.kind === "execution") {
    return action.title.startsWith("Buy")
      ? <ArrowDownToLine aria-hidden="true" size={16} />
      : <ArrowUpFromLine aria-hidden="true" size={16} />;
  }
  return <Target aria-hidden="true" size={16} />;
}

function actionLabel(state: DecisionAction["state"]): string {
  if (state === "review") return "Review required";
  if (state === "next_session") return "Next session";
  return "Completed";
}

function actionTone(state: DecisionAction["state"]): StatusTone {
  if (state === "review") return "negative";
  if (state === "next_session") return "warning";
  return "positive";
}

export function InvestmentCommandPage() {
  const navigate = useNavigate();
  const workspaces = useResearchWorkspaces();
  const workspace = workspaces.data?.[0];
  const queue = useResearchQueue(workspace?.id);
  const portfolios = useShadowPortfolios(workspace?.id);
  const operating = useInvestmentOperatingView(workspace?.id);
  const policy = useAutomationPolicy(workspace?.id);
  const runs = useResearchRuns(workspace?.id);
  const catalysts = useCatalystCalendar(workspace?.id, { horizonDays: 30 });

  const books = useMemo(
    () => summarizeStrategyBooks(portfolios.data ?? []),
    [portfolios.data],
  );
  const latestRunSummary = useMemo(
    () => latestLifecycleRun(runs.data ?? []),
    [runs.data],
  );
  const runDetail = useResearchRun(workspace?.id, latestRunSummary?.id);
  const latestRun = runDetail.data ?? latestRunSummary;
  const actions = useMemo(
    () => buildDecisionActions(latestRun, books),
    [books, latestRun],
  );
  const inbox = useMemo(
    () => researchInbox(queue.data?.candidates ?? []),
    [queue.data?.candidates],
  );
  const eventWatch = useMemo(
    () => upcomingCatalysts(
      catalysts.data?.events ?? [],
      new Date().toISOString().slice(0, 10),
    ),
    [catalysts.data?.events],
  );
  const observedBreaches = operating.data?.portfolios.reduce(
    (total, portfolio) => total + portfolio.risk.breachedLimits.length,
    0,
  ) ?? 0;
  const reviewCount = Math.max(
    actions.filter((action) => action.state === "review").length,
    observedBreaches,
  );
  const targetCount = actions.filter((action) => action.state === "next_session").length;
  const executionCount = actions.filter((action) => action.state === "completed").length;
  const dataFailure = queue.isError || portfolios.isError || operating.isError || policy.isError || runs.isError || runDetail.isError || catalysts.isError;
  const isLoading = workspaces.isLoading || (
    Boolean(workspace) &&
    [queue, portfolios, operating, policy, runs, runDetail, catalysts].some((query) => query.isLoading)
  );

  if (isLoading) {
    return (
      <div aria-label="Loading investment command" className="research-loading">
        <span className="research-loading__header" />
        <span className="research-loading__summary" />
        <span className="research-loading__body" />
      </div>
    );
  }

  if (workspaces.isError || !workspace) {
    return (
      <section className="research-unavailable">
        <DatabaseZap aria-hidden="true" size={26} />
        <h1>Investment command unavailable</h1>
        <p>The tenant-bound research workspace could not be loaded.</p>
        <Button onPress={() => workspaces.refetch()}>
          <RefreshCw aria-hidden="true" size={14} />Retry
        </Button>
      </section>
    );
  }

  return (
    <div className="investment-command">
      <header className="command-header">
        <div>
          <span className="command-header__eyebrow">Portfolio manager workspace · completed market evidence</span>
          <h1>Investment command</h1>
          <p>What requires action, what changed, what remains blocked, and how the paper books are behaving.</p>
        </div>
        <StatusBadge
          dot
          tone={policy.data?.lastRunStatus === "failed" ? "negative" : policy.data?.enabled ? "positive" : "warning"}
        >
          {automationHeadline(policy.data)}
        </StatusBadge>
      </header>

      <section aria-label="Investment process status" className="command-status-strip">
        <span>
          <DatabaseZap aria-hidden="true" size={15} />
          <small>Evidence cutoff</small>
          <strong>{dateTime(queue.data?.knowledgeCutoffAt)}</strong>
        </span>
        <span>
          <CheckCircle2 aria-hidden="true" size={15} />
          <small>Last completed cycle</small>
          <strong>{dateTime(latestRun?.completedAt)}</strong>
        </span>
        <span>
          <Clock3 aria-hidden="true" size={15} />
          <small>Next scheduled cycle</small>
          <strong>{dateTime(policy.data?.nextRunAt)}</strong>
        </span>
        <span>
          <Gauge aria-hidden="true" size={15} />
          <small>Mandate and benchmark</small>
          <strong>{operating.data ? `v${operating.data.mandate.version} · ${operating.data.mandate.benchmarkKey.replace(/_/g, " ")}` : `${researchDeployment.market} · ${researchDeployment.exchangeName}`}</strong>
        </span>
      </section>

      {dataFailure && (
        <section className="command-partial-warning">
          <AlertTriangle aria-hidden="true" size={16} />
          <span>
            <strong>Partial operating view</strong>
            One or more secured read models failed. Missing sections are not replaced with stale or cross-market data.
          </span>
        </section>
      )}

      <section aria-label="Decision summary" className="command-decision-strip">
        <button onClick={() => navigate("/portfolio")} type="button">
          <ShieldAlert aria-hidden="true" size={17} />
          <span><small>Risk review</small><strong>{reviewCount}</strong></span>
          <em>{reviewCount ? "Constraints need inspection" : "No new intervention"}</em>
        </button>
        <button onClick={() => navigate("/portfolio")} type="button">
          <Target aria-hidden="true" size={17} />
          <span><small>Next-session targets</small><strong>{targetCount}</strong></span>
          <em>{targetCount ? "Not filled yet" : "No target change"}</em>
        </button>
        <button onClick={() => navigate("/portfolio")} type="button">
          <CircleDollarSign aria-hidden="true" size={17} />
          <span><small>Paper executions</small><strong>{executionCount}</strong></span>
          <em>Latest completed cycle</em>
        </button>
        <button onClick={() => navigate("/queue")} type="button">
          <BookOpenCheck aria-hidden="true" size={17} />
          <span><small>Research attention</small><strong>{inbox.length}</strong></span>
          <em>Evidence work, not orders</em>
        </button>
      </section>

      <div className="command-layout">
        <main>
          <section className="atlas-panel command-blotter">
            <header>
              <span><strong>Decision blotter</strong><small>Risk first, future targets second, completed fills third</small></span>
              <Button onPress={() => navigate("/portfolio")} variant="quiet">
                Full ledger <ArrowRight aria-hidden="true" size={14} />
              </Button>
            </header>
            {actions.length === 0 ? (
              <div className="command-empty">
                <CheckCircle2 aria-hidden="true" size={20} />
                <span><strong>No new portfolio action</strong><small>The latest lifecycle produced no risk intervention, target transition, or paper fill.</small></span>
              </div>
            ) : actions.map((action) => (
              <button
                className={`command-action command-action--${action.state}`}
                key={action.id}
                onClick={() => navigate("/portfolio")}
                type="button"
              >
                <span className="command-action__icon">{actionIcon(action)}</span>
                <span className="command-action__body">
                  <small>{action.code ? `$${action.code}` : "Portfolio"} · {action.date ?? "Latest cycle"}</small>
                  <strong>{action.title}</strong>
                  <p>{action.detail}</p>
                </span>
                <StatusBadge tone={actionTone(action.state)}>{actionLabel(action.state)}</StatusBadge>
              </button>
            ))}
          </section>

          <section className="atlas-panel command-books">
            <header>
              <span><strong>Strategy books</strong><small>Separate hypotheses, capital, benchmarks, and promotion evidence</small></span>
              <Button onPress={() => navigate("/hypotheses")} variant="quiet">
                Strategy lab <ArrowRight aria-hidden="true" size={14} />
              </Button>
            </header>
            {books.length === 0 ? (
              <div className="command-empty">
                <LineChart aria-hidden="true" size={20} />
                <span><strong>No paper strategy book exists</strong><small>A strategy must pass its registered historical diagnostic before forward collection can begin.</small></span>
              </div>
            ) : (
              <div className="command-book-table">
                <div className="command-book-table__head">
                  <span>Strategy</span><span>NAV</span><span>Excess</span><span>Exposure</span><span>Drawdown</span><span>State</span>
                </div>
                {books.map((book) => (
                  <button key={book.id} onClick={() => navigate("/portfolio")} type="button">
                    <span><strong>{book.name}</strong><small>{book.strategyKey} · as of {book.asOfDate ?? "unknown"}</small></span>
                    <span className="command-book-metric"><small>NAV</small><strong>{money(book.nav)}</strong></span>
                    <span className="command-book-metric"><small>Excess</small><strong className={book.excessReturnPct >= 0 ? "value-up" : "value-down"}>{signed(book.excessReturnPct)}</strong></span>
                    <span className="command-book-metric"><small>Exposure</small><strong>{book.grossExposurePct.toFixed(1)}%</strong><em>{book.positionCount} positions</em></span>
                    <span className="command-book-metric"><small>Drawdown</small><strong className={book.drawdownPct > 10 ? "value-down" : ""}>{book.drawdownPct.toFixed(2)}%</strong></span>
                    <span className="command-book-metric"><small>State</small><StatusBadge tone={promotionTone(book.promotionStatus)}>{book.promotionStatus}</StatusBadge></span>
                  </button>
                ))}
              </div>
            )}
          </section>
        </main>

        <aside>
          <section className="atlas-panel command-research-inbox">
            <header>
              <span><strong>Research requiring attention</strong><small>Investigation urgency, never a buy ranking</small></span>
              <Button onPress={() => navigate("/queue")} variant="quiet" aria-label="Open research inbox">
                <ArrowRight aria-hidden="true" size={14} />
              </Button>
            </header>
            {inbox.length === 0 ? <p className="command-side-empty">No fresh evidence requires investigation.</p> : inbox.map((candidate) => (
              <button key={candidate.id} onClick={() => navigate(`/companies/${encodeURIComponent(candidate.ticker)}`)} type="button">
                <span><strong>${candidate.ticker}</strong><small>{candidate.company}</small></span>
                <span><strong>{candidate.status === "new_evidence" ? "New evidence" : "Review"}</strong><small>Urgency {candidate.priority}</small></span>
                <p>{candidate.queueReason}</p>
              </button>
            ))}
          </section>

          <section className="atlas-panel command-catalysts">
            <header>
              <span><strong>Catalyst watch</strong><small>Next 30 days · confirmed and inferred kept separate</small></span>
              <Button onPress={() => navigate("/catalysts")} variant="quiet" aria-label="Open catalyst calendar">
                <ArrowRight aria-hidden="true" size={14} />
              </Button>
            </header>
            {eventWatch.length === 0 ? <p className="command-side-empty">No scheduled catalyst is available in this horizon.</p> : eventWatch.map((event) => (
              <button key={event.id} onClick={() => navigate("/catalysts")} type="button">
                <CalendarClock aria-hidden="true" size={15} />
                <span><strong>${event.code} · {eventTypeLabel(event.eventType)}</strong><small>{timingLabel(event)}</small></span>
                <StatusBadge tone={event.timingKind === "confirmed" ? "positive" : "warning"}>{event.timingKind}</StatusBadge>
              </button>
            ))}
          </section>
        </aside>
      </div>
    </div>
  );
}
