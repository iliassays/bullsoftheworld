# Cross-venue dislocation product — research and product boundary, July 2026

Status: product discovery; no implementation or commercial launch approved.
Working description: a separate product that finds “buy cheaper here, sell higher there”
opportunities and calculates whether the spread remains executable after all costs and risks.

This is deliberately separate from Bulls Atlas. Atlas researches companies, evidence, hypotheses,
and portfolios. The proposed product researches **price dislocations between venues or related
instruments**. Shared identity, data-provenance, backtest, alerting, and audit infrastructure may be
reused, but product claims, data licenses, user journeys, and risk models must remain separate.

## Product thesis

Most public “arbitrage scanners” show a gross price difference. A useful product must show an
**executable net spread**:

```text
net spread =
sellable bid proceeds
- buyable ask cost
- trading fees
- withdrawal, transfer, settlement, borrow, financing, tax, and conversion costs
- expected slippage
- a risk reserve for latency, failure, cancellation, and inventory
```

If the product cannot observe executable bid/ask size, transfer state, account eligibility, and
costs, it should call the result a **dislocation candidate**, not an arbitrage.

The durable advantage would be normalization and truthfulness:

- prove that both listings represent the same deliverable asset or define the basis risk;
- use executable prices and available size, not headline last prices;
- show the capital and inventory needed on each venue;
- model every fee and delay;
- record whether the opportunity could actually have been completed;
- learn which venues, instruments, and time windows repeatedly produce realizable spreads.

## Opportunity classes

### 1. Crypto cross-exchange spot spreads

This is technically the closest to literal “buy the same asset cheaper on one exchange and sell it
higher on another.”

Advantages:

- continuous markets and widespread exchange APIs;
- standardized symbols can be normalized;
- bid/ask and book depth are often available;
- paper monitoring is straightforward.

Constraints:

- capital normally must be pre-funded on both exchanges; transferring after seeing the spread is
  often too slow;
- withdrawal suspensions, chain congestion, confirmation delays, stablecoin basis, and exchange
  failure can dominate the visible spread;
- country, KYC, custody, counterparty, tax, and regulatory eligibility differ;
- professional market makers already compete for obvious low-latency spreads.

Recommendation: feasible as a research MVP, but it should begin as a **paper opportunity ledger**
with no custody and no execution.

### 2. Retail and resale marketplace arbitrage

Examples include matching the same UPC/SKU across wholesale, retail, and resale marketplaces.

Advantages:

- slower competition than exchange trading;
- the edge can come from fragmented catalogs and local availability rather than microseconds;
- easier for a user to understand.

Constraints:

- product matching, condition, counterfeit, returns, shipping, sales tax/VAT, marketplace fees,
  inventory storage, account limits, and price changes;
- platform terms may restrict scraping or automated purchasing;
- a listed selling price is not guaranteed demand.

Recommendation: potentially the easiest standalone commercial product if it uses authorized APIs
or merchant feeds and models realized sell-through rather than calling every price difference
profit.

### 3. US securities relative-value dislocations

Candidate families include:

- ETF market price versus indicative portfolio value or underlying basket;
- closed-end fund discount/premium changes;
- ADR versus ordinary-share parity after FX, ratio, hours, tax, borrow, and conversion;
- merger consideration versus target price;
- dual share classes;
- convertible, warrant, option, and stock capital-structure relationships;
- statistically related pairs.

These are usually **relative-value or event-driven trades, not risk-free arbitrage**. US exchange
fragmentation in the same listed stock is already connected by professional routing, market makers,
Reg NMS protections, and low-latency infrastructure. A retail product should not promise durable
same-stock exchange arbitrage.

Recommendation: this is the best fit with Atlas infrastructure, but it should be marketed as a
research and monitoring product. Start with slower EOD/event dislocations, not latency competition.

### 4. Sportsbook or prediction-market price differences

Mathematically, opposing prices can sometimes create a locked or near-locked payoff.

Constraints include jurisdiction, geolocation, identity, stake limits, account closure, rule
differences, voided bets, market settlement definitions, and responsible-gambling obligations.

Recommendation: do not make this the first product. Legal and platform-operational complexity is
too central to the business model.

### 5. FX, remittance, gift-card, ticket, and local-goods spreads

These can show large apparent differences but frequently involve:

- capital controls or prohibited informal exchange;
- fraud, chargeback, identity, or stolen-value risk;
- nontransferable inventory;
- platform restrictions;
- manual logistics that do not scale.

Recommendation: exclude any flow that depends on bypassing currency, securities, payments, ticket,
or marketplace rules.

## Recommended product sequence

Do not launch a universal arbitrage engine. Build one vertical and prove realized execution.

### Discovery choice A — crypto paper monitor

Choose this if the goal is fastest technical validation:

- 3–5 reputable, legally accessible exchanges;
- 10–20 highly liquid spot pairs;
- no leverage, derivatives, custody, or automatic execution;
- normalized bid/ask depth, fees, transfer-network status, and inventory requirements;
- immutable opportunity and simulated-completion ledger.

Success means the net spread survives realistic latency and costs often enough to justify a later
execution study.

### Discovery choice B — US relative-value monitor

Choose this if the goal is maximum reuse of Bulls/Atlas infrastructure:

- closed-end fund discounts;
- ETF price/NAV and basket dislocations where licensed data exists;
- announced cash/stock merger spreads;
- selected ADR parity;
- option/stock relationships as research evidence.

Success means the product identifies persistent, explainable dislocations that improve a research
workflow. It should not be described as guaranteed arbitrage.

### Discovery choice C — marketplace resale intelligence

Choose this if the goal is a non-financial standalone SaaS:

- one product category with reliable identifiers;
- authorized catalog and price sources;
- shipping, marketplace fee, return, tax, condition, and sell-through model;
- user-entered inventory and capital limits;
- realized resale ledger.

Success means users repeatedly find inventory that sells at the modeled net margin.

## Shared platform components

The second product can reuse concepts, not Atlas conclusions:

- identity/security master for venues, instruments, pairs, SKUs, and deliverables;
- immutable raw-source snapshots;
- `effective_at`, `known_at`, and `ingested_at`;
- source and license registry;
- correction and stale-data handling;
- deterministic calculation engine;
- experiment registry and no-lookahead replay;
- alert deduplication;
- paper opportunity, simulated leg, realized leg, and failure ledger;
- audit events and user/workspace isolation.

It should not reuse:

- Atlas research-queue scores;
- Atlas company-thesis terminology;
- a stock-selection backtest as proof of arbitrage;
- customer-facing market data under an Atlas-only license;
- Atlas’s “validated” label without a separate spread-execution validation policy.

## Core data model

Each candidate should preserve:

- canonical asset/deliverable identity;
- buy venue, sell venue, account/region eligibility, and session status;
- buy ask, sell bid, sizes, timestamps, and quote age;
- currency and conversion path;
- trading, clearing, withdrawal, deposit, transfer, borrow, financing, shipping, platform, and tax
  cost assumptions;
- available inventory and capital on both sides;
- expected and worst-case completion time;
- cancellation, rejection, settlement, counterparty, custody, and basis risks;
- gross spread, net spread, net return on constrained capital, and capacity;
- whether both legs were simultaneously executable;
- later simulated or realized outcome.

## Product surfaces

1. **Opportunity monitor** — ranked candidates with net spread, capacity, age, and risk reserve.
2. **Leg inspector** — exact prices, costs, asset mapping, route, and failure modes.
3. **Capital map** — where prefunded inventory/cash is required and how much is trapped.
4. **Replay lab** — point-in-time historical or captured-book replay with latency and partial fills.
5. **Opportunity memory** — candidates, attempted legs, misses, failures, and realized net results.
6. **Venue health** — stale books, transfer suspensions, rejects, outages, and counterparty limits.

## Validation gates

No opportunity class should move beyond research unless:

- both legs use observable executable prices and size;
- all material costs are modeled;
- asset/deliverable identity is verified;
- latency and partial-fill risk are stressed;
- failed, rejected, cancelled, and uncompleted legs are retained;
- historical replay does not assume instantaneous transfer;
- performance survives a doubled-slippage/fee stress;
- capacity is reported;
- no single venue outage or one event explains the result;
- legal, data-license, platform-terms, tax, and account-eligibility reviews cover the exact workflow;
- a forward paper ledger confirms the historical result.

Automatic execution, custody, customer funds, broker/exchange credentials, or personalized trade
instructions require a separate security and regulatory program. They are not implied by a
successful scanner.

## Initial recommendation

Keep this as a second product and select the first vertical before implementation.

**Revisit trigger (deliberate parking, 2026-07-16):** this memo is shelf research. It is not
reconsidered for implementation until Bulls Atlas has shipped its paid alpha and the combined
market-data licensing review (Tiingo, Sharadar, Cboe) is closed. Until then it must not generate
backlog items. If picked up, discovery choice B (US relative-value monitor) is the preferred
vertical: maximum Atlas infrastructure reuse and the cleanest legal posture.

- For the fastest proof of the “same asset, two prices” concept: choose the crypto paper monitor.
- For strongest strategic fit with Bulls Atlas: choose the US slower relative-value monitor.
- For a broader non-financial SaaS opportunity: choose one resale-marketplace category.

The first build should be a captured-data and paper-opportunity system. The decision to connect
accounts or execute should come only after the product can demonstrate realized, net, capacity-aware
spreads rather than attractive screenshots.
