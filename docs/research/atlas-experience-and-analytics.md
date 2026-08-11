# Atlas orientation, help, and product analytics

Status: implemented 2026-08-12
Applies to: Bulls of Dhaka Atlas and Bulls of Wall Street Atlas

## Purpose

Atlas has a controlled investment workflow, but its terms are not self-evident. The experience
layer teaches the real five-stage process without changing strategy, risk, or execution logic:

1. Discover point-in-time observations.
2. Investigate the evidence and counter-evidence.
3. Validate a registered strategy and its promotion gates.
4. Allocate only through portfolio and risk controls.
5. Learn from immutable forward outcomes and calibration.

The orientation is offered once per tenant and user. It can always be replayed from the Help
control. Skipping is explicit and durable; the product does not force the tour on every session.

## Tenant boundary

All experience keys include both the deployment tenant and authenticated user id. A user completing
the DSE orientation or granting DSE analytics consent does not change the US account state, even if
the numerical user id happens to match. Product events are also tenant-bound by the API's
`X-Tenant-Host` validation and server-side tenant dependency.

Current orientation and consent preferences are stored in the browser. They are not yet synchronized
across devices. This is deliberate until Atlas has a general, tenant-scoped account-preferences API;
it avoids adding a one-off database field and does not weaken the fail-closed consent behavior.

## Persistent help

The top bar exposes an accessible Help control with three sections:

- **Workflow** links each stage to its authoritative workspace.
- **Glossary** is searchable and defines both what a term means and what it does not mean.
- **Privacy** displays and changes the analytics choice immediately.

The glossary covers evidence cutoff, setup confirmation, research urgency, counter-evidence,
registered strategy, promotion gates, targets, paper execution, planning objective, MFE, MAE,
forward outcomes, calibration, reconstructed evidence, and data-blocked states.

## Analytics contract

Atlas analytics are first-party and explicitly opt-in for every user and market. Unknown or denied
consent emits no event. Analytics failures never block navigation or research.

Allowed Atlas events:

- `atlas_onboarding_started`
- `atlas_onboarding_completed`
- `atlas_onboarding_skipped`
- `atlas_route_view`
- `atlas_workflow_stage_opened`
- `atlas_decision_surface_reached`
- `atlas_help_opened`
- `atlas_glossary_opened`

`atlas_decision_surface_reached` means the user reached Portfolio & Risk. It does not claim that a
decision, order, or trade occurred. Time is retained only as a coarse bucket (`under_2m`,
`2_to_10m`, or `over_10m`).

### Collected

- Tenant and market.
- A normalized route and workflow stage.
- Coarse entry point and elapsed-time bucket.
- Orientation/help version and bounded counts.
- A pseudonymous session identifier, keyed-hashed again on the server.

### Excluded

- Ticker symbols: `/companies/NXTC` is stored as `/companies/:ticker`.
- URL query strings.
- Research questions, notes, or other free-form text.
- Portfolio values, desired weights, positions, order details, or executions.
- Exact interaction timing.

The API allowlists event names and property keys, truncates bounded strings, and drops unknown
properties. The existing weekly retention task permanently deletes raw product events older than
180 days.

## Validation

- Frontend: 22 test files and 90 tests pass under both DSE and US build boundaries.
- API: growth-event validation suite passes; database persistence test remains opt-in.
- Production builds pass for both tenants.
- Desktop orientation, final consent step, Help workflow, and glossary search reviewed visually.
- Mobile orientation and Help reviewed at 390 x 844; viewport and document widths both remain
  exactly 390 px.
