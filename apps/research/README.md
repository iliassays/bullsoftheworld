# Bulls Atlas

**Evidence before conviction.**

Private institutional research workspace for Bulls of the World. The same application is built as
two isolated deployments:

- `research.bullsofdhaka.com` for DSE data and workflows, with `atlas.bullsofdhaka.com` as its
  branded alias;
- `research.bullsofwallst.com` for US data and workflows, with `atlas.bullsofwallst.com` as its
  branded alias.

The research application is separate from the public retail portals because its authorization,
evidence, workflow, and audit requirements are different. A deployment is permanently bound to one
tenant and one market; users cannot switch between DSE and US inside a workspace.

Private V1 enables the server-ranked Research Queue, evidence-first Company Dossier, bounded
Autonomous Analyst, registered Hypothesis Lab, no-broker Portfolio Intelligence, and immutable
Research Memory with forward calibration. Lifecycle Control coordinates these stages through an
explicit workspace policy and dedicated tenant-bound worker. Catalyst Calendar provides typed DSE
official dates and point-in-time US filing-cadence windows with explicit confidence, source links,
and lifecycle status. The existing organization schema does not imply that team invitations or
administration are already available.

US options intelligence is a planned, unimplemented Atlas evidence module. Its specification is
`../../docs/research/us-options-flow-research-2026-07.md`. It must separate directional delta,
volatility demand, opening/closing evidence, abnormality, liquidity, and stock/catalyst confirmation;
it is not a large-call alert or an authorization to trade options.

## Module boundaries

- `src/app`: composition, providers, and routing only.
- `src/layout`: authenticated workspace shell and navigation.
- `src/design-system`: accessible, domain-neutral UI primitives.
- `src/features/<feature>`: feature model, gateway, query hook, components, styles, and tests.
- `packages/core/.../models/research`: server-side research tenancy, runs, and evidence records.
- `packages/analytics/.../financial_reasoning.py`: provider-free finance rules, diagnostic lenses,
  conditional scenarios, disclosure semantics, and next-evidence requests.
- `packages/analytics/.../research_loop.py`: analyst/skeptic/verifier state machine and evidence gate.
- `packages/analytics/.../research_strategy.py`: registered signals, backtests, shadow execution,
  deterministic market risk policies, and objective paper-promotion gates.
- `services/api/.../institutional_research/worker.py`: exact-identity post-close lifecycle jobs;
  stale EOD inputs are refused and retried rather than silently accepted.

Feature components must not call `fetch` directly. Data access goes through a typed gateway and a
TanStack Query hook. Domain calculations such as filtering and queue summaries belong in the
feature model, where they can be unit tested independently of React.

The autonomous analyst does not require a human approver or a paid model. Finance Reasoner V2 can
qualify, monitor, reject, or abstain from the normalized fact ledger, but it cannot override
evidence, liquidity, position, sector, gross-exposure, cost, stop, or drawdown gates. An optional
future language model may explain or extract evidence through the same typed contract; it cannot
become the calculation, verification, or risk authority. Shadow portfolios never send an order to
a broker.

## Local development

```bash
cp .env.example .env.local
npm install
npm run dev
```

Set `VITE_RESEARCH_PREVIEW=true` only for interface development. Preview records are illustrative
and the interface labels them accordingly. With preview mode disabled, the app fails closed until
the secured research API is configured; it never substitutes demonstration records for private
workspace data.

## Deployment

Provision the dedicated S3, CloudFront, and Route 53 stack with a scoped AWS deployment role:

```bash
ATLAS_TENANT=bullsofdhaka \
ATLAS_AWS_PROFILE=bulls-atlas-deployer \
ATLAS_HOSTED_ZONE_ID=<route-53-zone-id> \
./infra/aws/deploy-atlas-infra.sh
```

Then publish an explicitly labelled preview:

```bash
ATLAS_AWS_PROFILE=bulls-atlas-deployer \
ATLAS_TENANT=bullsofdhaka \
ATLAS_S3_BUCKET=<stack-output-bucket> \
ATLAS_CLOUDFRONT_ID=<stack-output-distribution> \
ATLAS_PREVIEW=true \
ATLAS_ALLOW_PUBLIC_PREVIEW=yes \
./deploy-atlas.sh
```

Repeat with `ATLAS_TENANT=bullsofwallst` for the US deployment. Both scripts reject the AWS root
principal. Production mode uses the authenticated institutional research API and fails closed if
its tenant, market, site, or API configuration contradicts the selected tenant profile.

By default, each stack requests and DNS-validates an ACM certificate covering its canonical
`research.*` hostname and `atlas.*` alias. Set `ATLAS_CERTIFICATE_ARN` only to reuse an existing
us-east-1 certificate that covers both names.

## Verification

```bash
VITE_RESEARCH_TENANT=bullsofdhaka \
VITE_RESEARCH_MARKET=DSE \
VITE_RESEARCH_SITE_URL=https://research.bullsofdhaka.com \
VITE_RESEARCH_PORTAL_URL=https://bullsofdhaka.com \
VITE_RESEARCH_API_URL=https://api.bullsofdhaka.com \
npm run build
npm test
npm audit --audit-level=moderate
```

## Product guardrails

- Queue priority ranks analyst attention, not expected return.
- Conclusions must retain primary evidence, counter-evidence, and a knowledge cutoff.
- DSE and US share code and workflow contracts, but run as separate tenant-bound deployments with
  market-specific evidence adapters and server-side authorization.
- Tenant and workspace authorization is enforced server-side; frontend filtering is not a security
  boundary.
- The API runtime must use a non-owner PostgreSQL role with `NOBYPASSRLS`; database-owner sessions
  are reserved for migrations and controlled maintenance.
- DSE ownership is periodic reported composition, US 13F data is delayed quarterly disclosure, and
  FINRA daily short volume is not short interest. The UI must retain those limitations.
- New modules should represent a complete analyst workflow, not an isolated dashboard widget.
