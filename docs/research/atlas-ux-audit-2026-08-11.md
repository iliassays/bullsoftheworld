# Atlas UX audit - 2026-08-11

## Executive verdict

Atlas already had credible analytical surfaces, but its end-to-end workflow was not friendly enough.
The former Command page mixed portfolio actions, research urgency, full setup scanners, strategy
readiness, catalysts, and book performance in one long surface. That made a scanner observation
look closer to an investment decision than it is and forced experienced users to search for the
actual action state.

This release corrects the information architecture without changing trading calculations or
promotion rules. Atlas is now suitable for a private beta with research-aware users. It is not yet
a zero-training consumer product: users still need a short orientation to Atlas terminology and to
the difference between a setup, a strategy target, and a paper execution.

## Reviewed user journey

The normative path is:

1. Discover - inspect point-in-time setups and dated catalysts.
2. Investigate - open the research inbox and company evidence workbench.
3. Validate - evaluate a registered strategy, costs, robustness, and promotion gates.
4. Allocate - inspect risk, next-session targets, and paper executions.
5. Learn - review immutable forward outcomes and calibration.

A setup or urgent research item is never promoted directly into a paper order. A registered
strategy must generate a target and pass evidence, liquidity, sizing, exposure, and risk controls.

## Information architecture

### Investment

- **Command**: current action state, in this order: risk, targets, executions, research attention.
- **Portfolio and risk**: target, position, execution, exposure, and constraint ledger.
- **Strategy lab**: registered hypotheses, backtests, forward books, and promotion evidence.
- **Research outcomes**: immutable run ledger and forward calibration.

### Research

- **Research inbox**: investigation priority; never a return or buy ranking.
- **Setup monitor**: point-in-time chart-pattern lifecycles and counter-evidence.
- **Condition scanner**: deterministic market and security conditions.
- **Company research**: evidence-led company investigation.
- **Catalysts**: confirmed dates and explicitly labelled inferred windows.

### Operations

- **Automation and audit**: schedule, policy, run state, and immutable operational ledger.

## Changes in this release

- Moved the full Setup Monitor and Strategy Readiness views off Command into `/setups`.
- Put the decision summary and Agent Decisions at the top of Command.
- Added a compact, expandable workflow map linking every decision stage.
- Exposed Research Outcomes in primary navigation and removed a dead Settings control.
- Renamed Today to Command and Research Memory to Research Outcomes.
- Made the longer sidebar scroll independently on constrained desktop heights.
- Added responsive workflow layouts and verified 390 px mobile pages without body overflow.
- Corrected preview fixture contradictions so row state, lifecycle endpoint, chart close, trigger,
  invalidation, and tenant all agree.
- Added explicit preview calibration data instead of allowing the preview-only Outcomes page to
  fail against an unavailable API.
- Parameterized API boundary tests so the same suite verifies DSE and US isolation in both
  directions.
- Added a one-time, replayable five-stage orientation tied to the actual Atlas workflow.
- Added a persistent, searchable Help center with explicit `Meaning` and `Not` definitions.
- Added fail-closed, first-party workflow analytics with per-tenant/user consent, sanitized routes,
  bounded properties, pseudonymous sessions, and the existing 180-day deletion policy.

## UX and evidence guardrails

- `Confirmed` on Setup Monitor means a deterministic setup rule completed. It does not mean high
  probability, strategy eligibility, a target, an execution, or profit.
- Research urgency determines what should be investigated first. It is not expected return.
- Planning objectives are risk references, not forecasts.
- Paper activity remains visibly separate from research observations.
- Historical/reconstructed evidence must retain its method and survivorship limitations.
- Missing datasets remain explicit blocked states; Atlas must not invent substitutes.
- DSE and US remain separate build, API, tenant, workspace, and authorization boundaries.

## Validation

- DSE test configuration: 22 files, 90 tests passed.
- US test configuration: 22 files, 90 tests passed.
- DSE production build: passed.
- US production build: passed.
- Desktop visual review: Command, Setup Monitor, and Research Outcomes.
- Mobile visual review: DSE Command and US Setup Monitor at a real 390 x 844 device viewport.
- Both mobile documents stayed exactly 390 px wide; only the intentionally closed navigation drawer
  was off-canvas.

## Recommended next improvements

1. Observe workflow-stage funnels and coarse time-to-Portfolio behavior before changing navigation.
2. Add empty-state exit events only where a named empty state has a real next action; do not infer
   successful completion from a route change.
3. Add role-based default views only after observing real portfolio-manager and analyst behavior.
4. Synchronize orientation and consent across devices only as part of a general tenant-scoped
   account-preferences API.
5. Continue replacing abbreviated score labels with visible definitions at the point of use.

The next product step should be measured onboarding and comprehension, not another scanner or
dashboard panel.
