import { Activity, ArrowRight, CircleHelp, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";

import { AppTooltip, StatusBadge } from "../../design-system";
import type { DecisionTicket } from "./decision-ticket";

function percentage(value: number | null): string {
  return value === null ? "Not registered" : `${value.toFixed(1)}%`;
}

export function DecisionTicketPanel({ ticket }: { ticket: DecisionTicket }) {
  return (
    <section className={`decision-ticket decision-ticket--${ticket.tone}`}>
      <header>
        <div>
          <span className="decision-ticket__eyebrow">
            <Activity aria-hidden="true" size={13} />
            Decision ticket
            <AppTooltip label="This panel reconciles the research conclusion with the append-only strategy, target, execution, position, and risk ledger. Research qualification alone never creates an order.">
              <button aria-label="Explain decision ticket" type="button">
                <CircleHelp aria-hidden="true" size={12} />
              </button>
            </AppTooltip>
          </span>
          <h2>{ticket.label}</h2>
          <p>{ticket.rationale}</p>
        </div>
        <div className="decision-ticket__state">
          <StatusBadge dot tone={ticket.tone}>{ticket.action.replace("_", " ")}</StatusBadge>
          <small>
            {ticket.source === "portfolio_ledger"
              ? "Verified from portfolio ledger"
              : ticket.source === "research_record"
                ? "Research record only"
                : "No decision record"}
          </small>
        </div>
      </header>

      <div className="decision-ticket__grid">
        <article>
          <span>Book and strategy</span>
          <strong>{ticket.portfolioName ?? "No active shadow book"}</strong>
          <small>{ticket.strategyKey ?? "No registered strategy"}</small>
        </article>
        <article>
          <span>Exposure</span>
          <strong className="tnum">{percentage(ticket.currentWeightPct)}</strong>
          <small>Target {percentage(ticket.targetWeightPct)}</small>
        </article>
        <article>
          <span>Execution state</span>
          <strong>{ticket.effectiveDate ?? "No order date"}</strong>
          <small>{ticket.execution}</small>
        </article>
        <article>
          <span>Thesis guardrail</span>
          <strong>Explicit invalidation</strong>
          <small>{ticket.invalidation}</small>
        </article>
        <article>
          <span>Portfolio risk</span>
          <strong><ShieldCheck aria-hidden="true" size={13} /> Mandate check</strong>
          <small>{ticket.risk}</small>
        </article>
        <article>
          <span>Next review</span>
          <strong>Evidence-driven</strong>
          <small>{ticket.nextReview}</small>
        </article>
      </div>

      <footer>
        <span>Research conclusion → strategy target → risk gate → modeled execution → position</span>
        <Link to="/portfolio">Open portfolio ledger <ArrowRight aria-hidden="true" size={13} /></Link>
      </footer>
    </section>
  );
}
