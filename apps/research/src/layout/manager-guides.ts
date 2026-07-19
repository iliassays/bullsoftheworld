export interface ManagerGuide {
  section: string;
  question: string;
  workflow: readonly [string, string, string];
  managerDecision: string;
  boundary: string;
  fieldNote?: string;
}

const GUIDES = {
  today: {
    section: "Today",
    question: "What changed after the latest completed DSE session, and what actually needs a decision?",
    workflow: [
      "Atlas freezes the latest completed-session evidence cutoff.",
      "It separates new evidence, active theses, risk exceptions, and blocked work.",
      "The manager reviews only changes that can alter capital, risk, or the research queue.",
    ],
    managerDecision: "Decide what deserves deeper work, what requires a risk response, and what remains unchanged.",
    boundary: "A ranked item is research priority—not a forecast, recommendation, or executed order.",
    fieldNote: "A +25% target is a pre-registered exit rule, not a claim that upside ends there. Re-entry requires a fresh qualifying signal after exit and cooldown.",
  },
  portfolio: {
    section: "Portfolio & risk",
    question: "What do we own, what can hurt us, and how much capital is genuinely available?",
    workflow: [
      "Executed events rebuild cash, unsettled receivables, lots, holdings, fees, and NAV.",
      "Prices mark exposure while mandate limits test concentration, liquidity, drawdown, and stress.",
      "Reconciliation compares the event ledger with the latest portfolio projection before decisions are trusted.",
    ],
    managerDecision: "Approve de-risking, reject concentration, and preserve liquidity before considering new upside.",
    boundary: "Cash, unsettled proceeds, target weights, and executed holdings are different things and must never be combined.",
    fieldNote: "Inception capital is immutable for an audited book. A BDT 300,000 experiment must start as a new comparison book; it must not rewrite a BDT 10,000,000 history.",
  },
  hypotheses: {
    section: "Strategy lab",
    question: "Does a fixed, reproducible idea survive costs, chronology, regimes, and honest failure tests?",
    workflow: [
      "Write the signal, universe, execution, sizing, exit, and invalidation rules before seeing results.",
      "Run chronological train, validation, and test windows with fees, slippage, liquidity, and settlement.",
      "Register every attempt, including failures, then require genuine forward evidence before promotion.",
    ],
    managerDecision: "Choose whether to reject, revise as a new version, keep diagnostic, or admit to a bounded forward trial.",
    boundary: "Backtest return and win rate alone are not edge; payoff, drawdown, sample size, excess return, and data integrity matter together.",
    fieldNote: "The DSE Quality Reversal rules are already implemented and archived. Its historical attraction was the combination of hit rate and right-skewed payoff—not 58% wins in isolation.",
  },
  queue: {
    section: "Research inbox",
    question: "Which companies deserve scarce analyst time first, and why are they in the queue?",
    workflow: [
      "Observable DSE securities are filtered by mandate and minimum evidence quality.",
      "Changed fundamentals, valuation, price behavior, ownership, and catalysts create research priority.",
      "Analyst, skeptic, and verifier passes turn priority into source-linked claims and open questions.",
    ],
    managerDecision: "Allocate analyst attention, not capital; demand the missing evidence before advancing a case.",
    boundary: "Queue rank measures urgency and evidence relevance. It is not expected return or conviction.",
  },
  companies: {
    section: "Company research",
    question: "What is known about this company, when was it knowable, and what would falsify the thesis?",
    workflow: [
      "Atlas assembles price, reported fundamentals, disclosures, ownership, and catalysts at a stated knowledge cutoff.",
      "Claims remain linked to evidence while supportive and contradictory facts are kept together.",
      "Scenarios, valuation, risks, and invalidation conditions are reviewed as one decision dossier.",
    ],
    managerDecision: "State the thesis, counter-thesis, price paid, time horizon, and evidence that would make us exit.",
    boundary: "A current database value is not automatically point-in-time historical evidence; publication and knowledge times control what a past decision could know.",
  },
  catalysts: {
    section: "Catalysts",
    question: "What event could change the market's information set, and how certain is its timing?",
    workflow: [
      "Official dated events are separated from windows inferred from reporting cadence.",
      "Each event is linked to the affected thesis, expected mechanism, and source confidence.",
      "After the event, Atlas records what actually changed instead of preserving the pre-event story.",
    ],
    managerDecision: "Decide whether event risk is rewarded, already priced, untradeable, or too uncertain to size.",
    boundary: "A catalyst can move price in either direction; calendar proximity is not directional edge.",
  },
  operations: {
    section: "Automation & audit",
    question: "Did the research process run completely, on time, and without inventing knowledge or fills?",
    workflow: [
      "Post-close jobs pin a completed DSE session and immutable evidence cutoff.",
      "Every research, backtest, target, execution, outcome, and reconciliation step records status and blockers.",
      "Failed data or risk gates stop promotion while the audit trail remains visible.",
    ],
    managerDecision: "Intervene on failed controls; never override a data blocker merely to produce activity.",
    boundary: "A successful job means the process ran as specified. It does not mean the strategy made money.",
  },
  memory: {
    section: "Research memory",
    question: "What did we believe, what happened afterward, and where is our process systematically wrong?",
    workflow: [
      "Atlas fingerprints each thesis and its evidence so later edits cannot erase the original decision state.",
      "Outcomes mature on fixed 5-, 20-, and 60-session horizons and are compared with the original claims.",
      "Calibration exposes repeated misses, regime dependence, and evidence sources that add or destroy value.",
    ],
    managerDecision: "Change the process only when repeated, comparable evidence supports the change.",
    boundary: "Memory is an anti-hindsight system. It should preserve embarrassing misses as carefully as successful calls.",
  },
} satisfies Record<string, ManagerGuide>;

export function managerGuideForPath(pathname: string): ManagerGuide {
  if (pathname.startsWith("/portfolio")) return GUIDES.portfolio;
  if (pathname.startsWith("/hypotheses")) return GUIDES.hypotheses;
  if (pathname.startsWith("/queue")) return GUIDES.queue;
  if (pathname.startsWith("/companies")) return GUIDES.companies;
  if (pathname.startsWith("/catalysts")) return GUIDES.catalysts;
  if (pathname.startsWith("/operations") || pathname.startsWith("/lifecycle")) return GUIDES.operations;
  if (pathname.startsWith("/memory")) return GUIDES.memory;
  return GUIDES.today;
}
