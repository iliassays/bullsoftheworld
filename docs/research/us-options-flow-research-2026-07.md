# US options-flow research for Bulls Atlas — July 2026

Status: research specification approved for historical evaluation. The fail-closed Phase A
entitlement, immutable-object, strict Option Sentiment v1.4 parser, Parquet normalization, quality
manifest, and manual import foundation are implemented as of 2026-07-16. No licensed file has been
loaded and no serving, feature, backtest, or customer-display module is enabled.
Market: US listed equity options and their US-listed underlying stocks only.
Product: Bulls Atlas / Bulls of Wall Street.

This document defines how options-chain and options-flow evidence may enter Atlas without turning
the product into an “unusual calls” alert service. Read it with
`docs/architecture/institutional-research-os.md` and
`docs/research/us-market-data-strategy-2026-07.md`.

## Decision

Add options intelligence to Atlas as a **separate US evidence lens**. Initially it may:

- improve research-queue priority;
- add positioning, volatility, skew, term-structure, liquidity, and event context to a company
  dossier;
- create testable hypotheses in Hypothesis Lab;
- record whether the evidence helped or failed in Research Memory.

It may not initially:

- emit a buy/sell recommendation;
- describe a large call trade as automatically bullish;
- claim that volume above displayed open interest proves a new position;
- size a portfolio position;
- send an order to a broker;
- describe a backtest as validated before the normal Atlas point-in-time, holdout, cost, capacity,
  inactive/delisted-universe, and forward-paper gates pass.

The first strategy research should use options flow to rank **underlying common stocks**, not to buy
options. This isolates whether the information has stock-selection value before adding option
spread, volatility, decay, exercise, assignment, and expiration effects.

**Universe tension (stated deliberately):** the testable options universe is the most liquid
optionable equities, which is largely *not* the Atlas small/micro-cap wedge — most wedge names have
no liquid listed options. This module therefore extends Atlas coverage toward liquid mid/large-cap
names where competitors are strongest; it must not become the product's center of gravity. Options
intelligence remains sequenced behind the core evidence modules (catalysts, forensics, universe
breadth) and, where the wedge is concerned, its main contribution is the *absence* signal: an
explicit `no_liquid_options` state on small-cap dossiers, never a coerced zero.

## Why this belongs in Atlas

Peer-reviewed US research provides a credible reason to test the signal:

- Pan and Poteshman found that buyer-initiated opening option volume contained information about
  future stock returns in their 1990–2001 sample. Low open-buy put/call-ratio stocks outperformed
  high-ratio stocks by more than 40 basis points on the next day and more than 1% over the next
  week. The important caveat is that the strongest result used nonpublic opening-position data;
  publicly inferred trade direction became much weaker after exact opening data was included.
- Ge, Lin, and Pearson found that purchases of calls opening new positions were the strongest
  predictor among the signed option-volume components they studied. They also excluded expiration
  weeks from their main tests because rolling activity can look like new information.
- Hu found that delta-weighted option-induced stock imbalance predicted next-day stock returns in a
  historical US sample.

The literature does not justify a naive alert:

- Muravyev found that market-maker inventory risk has a first-order effect on option prices and is
  larger than the asymmetric-information component.
- Bryzgalova, Pavlova, and Sikorskaya documented that modern US retail options activity is heavily
  concentrated in short-dated, high-relative-spread contracts and that retail traders lost money on
  average in their sample.
- A 2026 Journal of Econometrics paper decomposes informed options activity into stock-value and
  volatility information. Large straddle-like or vega-heavy flow can be informative without being
  directionally bullish or bearish for the stock.
- A 2026 working paper finds that conventional quote-based trade classifiers can systematically
  misidentify customer demand because customers also supply resting limit orders.

The Atlas opportunity is therefore not “detect large trades.” It is to create a point-in-time,
auditable classifier that separates directional demand, volatility demand, hedging, closing, and
complex-order risk, then tests whether the resulting evidence adds value beyond ordinary stock
signals.

## Research questions

Atlas should answer five different questions and never collapse them into one score:

1. **Direction:** did the observed option activity create positive or negative underlying delta?
2. **Volatility:** was the activity primarily buying or selling volatility rather than expressing a
   stock-price direction?
3. **Position lifecycle:** was customer activity opening, closing, or impossible to determine?
4. **Abnormality:** was the activity unusual for this underlying, tenor, moneyness, and event state?
5. **Confirmation:** did completed-session stock price, relative strength, liquidity, filings, and
   catalysts support or contradict the options interpretation?

An Atlas research artifact should preserve those answers separately, with source, cutoff, method,
confidence, and reasons for abstention.

## Data contract

Options intelligence needs three data layers. One vendor product does not automatically satisfy all
three.

### 1. Underlying-level EOD sentiment

Cboe Option Sentiment is the preferred first historical evaluation feed because it supplies one
daily underlying-level record with fields including:

- net option delta for directional trades;
- call and put premium bought and sold;
- calls and puts bought;
- 30- and 90-day implied volatility;
- 20-day historical volatility;
- total vega traded;
- customer, firm, and market-maker volume;
- exchange-volume breakdowns;
- implied borrow;
- normalized 30-day 25-delta skew;
- size, days-to-expiration, and moneyness buckets and recent baselines.

This is suitable for a first cross-sectional stock-selection test. It is not a substitute for a
full option chain and does not by itself provide exact customer buy/sell/open/close records.

### 2. EOD option-chain snapshot

The dossier’s actual chain surface needs point-in-time contract rows:

- OCC-compatible option identifier and underlying identifier;
- as-of timestamp and source timestamp;
- expiration, strike, call/put, exercise style, and contract multiplier;
- bid, ask, quote sizes, last trade, volume, and previous-settlement open interest;
- underlying reference price;
- implied volatility, delta, gamma, theta, and vega, with calculation source/version;
- data-quality, stale-quote, crossed-market, no-bid, and liquidity flags.

Cboe Option EOD Summary or a commercially licensed OPRA-derived vendor should be evaluated for this
layer. Chain display and retention require explicit display/redistribution terms; an internal
research license is insufficient for a customer-facing Atlas surface.

### 3. Participant and position classification

Cboe Open-Close Volume Summary provides the most valuable research labels available in the current
plan:

- participant type: customer, professional customer, broker-dealer, or market maker;
- action: buy or sell;
- position: open or close;
- customer/professional-customer size bucket;
- contract-level series aggregation.

It covers Cboe exchanges rather than the entire US options industry, so Atlas must expose venue
coverage and must test whether the partial-market measurement remains representative. The EOD files
arrive after midnight US Eastern, which means any historical strategy must enter no earlier than
the next observable eligible stock price.

Full-market OPRA trades and NBBO quotes remain useful for intraday research, but standard OPRA does
not reveal the economic customer side or opening/closing status directly. An inferred OPRA
classifier must retain a confidence score and cannot be treated as equivalent to exact Open-Close
labels.

## Point-in-time and provenance rules

Every chain or flow observation requires:

- `effective_at`: the trade, quote, or session time described;
- `known_at`: when Atlas could first have received the complete record;
- `ingested_at`;
- source dataset, exchange coverage, delivery schedule, and license entitlement;
- raw content/object hash and normalization version;
- underlying and contract identity version;
- corporate-action adjustment policy;
- Greeks/model version and interest-rate/dividend inputs when Atlas or a vendor calculates them.

Open interest is especially sensitive. OCC states that displayed open-interest figures are derived
from the previous day’s settlement. Atlas must therefore label it `previous_settlement_open_interest`
or equivalent. Same-day volume greater than that number does not prove a new opening position, and
next-day open-interest changes cannot be used in a same-day backtest.

## Derived evidence

The first feature registry should contain interpretable, versioned measures rather than a black-box
score.

### Directional demand

- `net_directional_delta_usd`
- `net_directional_delta_to_stock_adv`
- `customer_open_buy_call_delta_usd` when exact labels exist
- `customer_open_buy_put_delta_usd` when exact labels exist
- `call_premium_imbalance`
- `put_premium_imbalance`
- `directional_delta_z_20`
- `directional_delta_z_60`

A positive value means the classified option activity created positive stock-equivalent delta under
the registered convention. It does not by itself mean an informed investor expects the stock to
rise.

### Volatility and distribution

- `iv30_minus_hv20`
- `iv90_minus_iv30`
- `normalized_25d_skew_30`
- one-, five-, and twenty-session changes in skew;
- `vega_to_directional_delta`;
- potential straddle/strangle concentration;
- event-relative volatility percentile;
- post-earnings volatility-crush context.

Directionally ambiguous, high-vega activity belongs in a volatility interpretation and must not
trigger the directional stock-flow label.

### Abnormality and concentration

- premium, contracts, delta, and vega versus 20/60-session baselines;
- concentration by expiration, strike, moneyness, and trade-size bucket;
- fraction in 0DTE, 1–7 DTE, 8–30 DTE, 31–60 DTE, and longer tenors;
- fraction in far-OTM, near-ATM, and deep-ITM contracts;
- customer versus professional/customer/firm/market-maker mix;
- Cboe-observed volume divided by total industry volume when both are licensed and point-in-time.

### Confirmation and contradiction

- completed-session stock return and range position;
- SPY- and sector-relative strength;
- stock dollar volume and abnormal volume;
- gap, trend, and distance from registered support/resistance measures;
- proximity to earnings and confirmed catalysts;
- recent SEC filing, offering, dilution, insider, beneficial-owner, short-interest, and FINRA
  activity evidence;
- option-chain liquidity and likely implementation cost.

The options lens must show contradictions. Bullish classified flow alongside a shelf offering,
financing risk, negative price response, or extremely illiquid chain is not “confirmed bullish
flow.”

## False-positive taxonomy

Atlas must attempt to detect, downgrade, or abstain on:

- covered-call writing and call overwriting;
- protective puts, collars, and portfolio hedges;
- vertical, calendar, diagonal, butterfly, condor, straddle, and strangle structures;
- rolls around expiration;
- conversions, reversals, box spreads, dividend trades, and synthetic financing;
- deep-ITM stock-substitution trades;
- market-maker facilitation and subsequent inventory hedging;
- ETF/index hedges incorrectly attributed to a single-name view;
- earnings-volatility trades;
- short-dated retail speculation;
- duplicated or corrected prints;
- stale, crossed, locked, no-bid, or extremely wide quotes;
- corporate actions and adjusted-contract deliverables.

An isolated transaction must not be reconstructed into a multi-leg structure unless timestamps,
sizes, venues/conditions, prices, and economic relationships satisfy a registered matching rule.
The original legs and matching confidence remain visible.

## Atlas workflow integration

### Research Queue

Options evidence may add transparent dimensions:

- directional-flow abnormality;
- volatility-demand abnormality;
- skew/term-structure change;
- event concentration;
- chain liquidity;
- classification confidence;
- contradictory-flow penalty.

The queue remains a research-priority list. “High directional-flow abnormality” is not a forecast.

### Company Dossier

Add an **Options intelligence** lens with:

1. evidence cutoff and market coverage;
2. chain liquidity and data-quality summary;
3. directional delta and premium interpretation;
4. volatility, skew, and term structure;
5. tenor/moneyness/size concentration;
6. opening/closing and participant evidence when licensed;
7. likely complex/hedge explanations;
8. stock, catalyst, and filing confirmation or contradiction;
9. historical percentiles and subsequent-outcome calibration;
10. explicit unknowns and abstention.

The chain itself is evidence, not merely a table. Default views should emphasize liquidity, tenor,
moneyness, IV, delta, volume, and previous-settlement open interest while allowing the user to
inspect the source rows.

### Catalyst Calendar

Record options evidence around confirmed events but keep two hypotheses separate:

- directional positioning before or after the event;
- volatility demand and expected-move repricing.

Do not infer an undisclosed event merely because option activity is unusual.

### Hypothesis Lab

The first registered experiment should be:

> Rank liquid US common stocks by customer opening directional delta when exact labels exist, or by
> the best licensed directional-delta proxy otherwise; require completed-session stock confirmation;
> enter the underlying stock at the next observable eligible price; hold for fixed 1/3/5/10-session
> horizons; compare with stock-only baselines.

The experiment should test incremental variants:

1. stock momentum/liquidity baseline;
2. options-only directional evidence;
3. options plus stock confirmation;
4. options plus stock confirmation plus catalyst/filing filters;
5. exact Open-Close labels versus inferred public trade classification;
6. event and non-event samples separately;
7. expiration weeks separately;
8. long-only and diagnostic long/short portfolios separately.

No user-created arbitrary Python is executed. Features and filters must be registered in the Atlas
strategy DSL and trial ledger.

### Research Memory

Persist the original interpretation and later outcomes:

- 1/3/5/10/20-session stock returns;
- benchmark-relative returns;
- maximum adverse and favorable excursion;
- realized volatility versus the observed implied-volatility state;
- whether the original flow classification was later supported by open-interest changes, without
  rewriting what was knowable at decision time;
- calibration by confidence, data source, event state, tenor, and liquidity bucket.

## Backtest design

Use temporal, untouched evaluation:

- 2019–2022: discovery and feature registration;
- 2023–2024: validation and parameter stability;
- 2025–June 2026: untouched holdout;
- then at least 8–12 weeks of forward paper observation.

**This design requires ~7 years of history and therefore exceeds the Phase A data purchase.**
Phase A's ~1-year Option Sentiment order is a schema/data-quality feasibility audit only — it cannot
run this temporal design. The multi-year history purchase needed for the registered experiment is a
separate, explicitly gated decision taken after Phase A passes and after the full Cboe cost stack
(Sentiment history + Option EOD Summary + Open-Close) has been priced in the combined licensing
review. Do not shrink the temporal design to fit one year of data.

The initial universe should be common stocks only, excluding indices, ETFs, preferreds, warrants,
funds, adjusted/nonstandard contracts, and names that fail the registered stock and option
liquidity floors. Start with approximately the most liquid 500–1,000 optionable equities, but let
point-in-time eligibility determine the actual daily universe.

Execution assumptions:

- EOD source formed on session `T`;
- no fill before session `T+1`;
- test next official open and the first-15-minute stock VWAP where licensed data permits;
- include opening gaps, spread, slippage, commissions, borrow for diagnostic shorts, and failed
  liquidity/capacity orders;
- do not use an option close or midpoint that was unavailable to the strategy;
- trade the stock in the first experiment.

Report:

- mean and median excess return;
- hit rate with confidence intervals;
- information coefficient and monotonic rank-bucket behavior;
- annualized return, volatility, Sharpe, Sortino, drawdown, turnover, and capacity;
- performance by year, volatility regime, sector, market-cap tier, liquidity, event state, tenor,
  and classification confidence;
- exposure to beta, size, value, momentum, quality, and short-term reversal;
- contribution concentration by ticker, date, sector, and catalyst;
- trial count, sensitivity, multiple-testing adjustment, and deflated performance measures.

The historical academic magnitudes are research motivation, not expected current returns. Atlas
must not use them in marketing or set its validation threshold by copying an old in-sample result.

## Promotion gates

Options-derived evidence remains `diagnostic` unless:

- source licensing permits the tested use;
- the underlying universe is point-in-time and includes inactive/delisted names;
- known-at timestamps prevent EOD delivery and open-interest leakage;
- chain identity, corporate actions, and adjusted contracts reconcile;
- signal rank buckets are reasonably monotonic in the untouched holdout;
- performance is positive after registered costs and after a doubled-slippage stress;
- no single ticker, sector, event week, or calendar year explains the result;
- the options feature adds value beyond the stock-only baseline;
- results survive event/non-event, expiration/non-expiration, and liquidity breakdowns;
- the exact strategy completes the normal Atlas forward-paper gate.

If exact Open-Close labels materially outperform inferred OPRA classification, Atlas should prefer
the slower, cleaner EOD research product rather than market a noisier real-time alert.

## Delivery phases

### Phase A — historical feasibility

Phase A proves schema, identity, and data quality — it does **not** authorize the strategy backtest,
whose multi-year history purchase is gated separately (see Backtest design).

Engineering status: the import foundation is implemented and disabled by default. Vendor
subscription/terms, a production object-storage bucket, an approved entitlement row, the historical
files, and the completed feasibility report remain outstanding. The resumable historical importer
and immutable descriptive evaluator are implemented; operational instructions are in
`docs/runbooks/us-options-phase-a.md`.

- license approximately one year of Cboe Option Sentiment as a low-cost schema/data-quality audit;
- obtain sample/quote for Option EOD Summary and Open-Close;
- reconcile symbols, sessions, blank fields, corporate actions, and coverage;
- build an immutable Parquet research set outside the API database;
- run descriptive distributions before any strategy test.

### Phase B — Atlas evidence lens

- ingest the approved EOD underlying-level data;
- add options provenance and feature registry;
- expose the dossier lens only when freshness, coverage, and license gates pass;
- label unavailable and illiquid data explicitly; never coerce blank fields to zero.

### Phase C — registered stock-selection experiment

- implement the registered options-confirmation strategy in Hypothesis Lab;
- run discovery, validation, untouched holdout, sensitivity, and cost stress;
- create a no-broker shadow book only if the diagnostic gates pass.

### Phase D — full chain and exact classification

- add the licensed chain snapshot;
- add Cboe Open-Close participant/action/position evidence;
- test whether exact labels improve the signal enough to justify their cost;
- reconstruct complex orders only through versioned, evaluated rules.

### Phase E — intraday research, only if justified

- evaluate full-market OPRA trades/NBBO;
- benchmark inferred classification against exact labels where overlap exists;
- measure whether earlier alerts retain incremental value after latency, corrections, and execution
  costs;
- do not build real-time infrastructure merely because it looks more active in the UI.

## Commercial and regulatory boundary

Internal research, customer-facing display, derived-data distribution, alerts, and automated
trading can carry different vendor and regulatory obligations.

- Cboe states that raw Open-Close data is for internal use and that external distribution of
  derived data requires additional licensing and approval.
- OPRA-derived real-time display, non-display processing, and redistribution can have separate
  agreements and fees.
- A personal or internal Atlas research tool is materially different from a service that sends
  personalized recommendations or automatically trades unaffiliated customer accounts.
- Any broker integration, personalized advice, or third-party auto-trading requires a new legal,
  broker-compliance, security, and product review. It is outside this specification.

## Primary references

Academic:

- Pan and Poteshman, “The Information in Option Volume for Future Stock Prices,” *Review of
  Financial Studies* (2006):
  https://academic.oup.com/rfs/article-abstract/19/3/871/1646711
- Hu, “Does option trading convey stock price information?”, *Journal of Financial Economics*
  (2014): https://www.sciencedirect.com/science/article/pii/S0304405X13003048
- Ge, Lin, and Pearson, “Why does the option to stock volume ratio predict stock returns?”,
  *Journal of Financial Economics* (2016):
  https://www.sciencedirect.com/science/article/abs/pii/S0304405X16000167
- Johnson and So, “The option to stock volume ratio and future returns,” *Journal of Financial
  Economics* (2012):
  https://www.sciencedirect.com/science/article/pii/S0304405X12000797
- Muravyev, “Order Flow and Expected Option Returns,” *Journal of Finance* (2016):
  https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12380
- Bryzgalova, Pavlova, and Sikorskaya, “Retail Trading in Options and the Rise of the Big Three
  Wholesalers,” *Journal of Finance* (2023):
  https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.13285
- “Decomposing informed trading in equity options,” *Journal of Econometrics* (2026):
  https://www.sciencedirect.com/science/article/pii/S0304407625001824
- Grauer, Schuster, and Uhrig-Homburg, “Unmasking Option Demand: New Classification Methods and
  Stock Return Predictability,” working paper, revised May 2026:
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4098475

Market data and risk:

- Cboe Option Sentiment specification:
  https://datashop.cboe.com/Documents/Cboe_OptionSentiment_Specs.pdf
- Cboe Open-Close Volume Summary:
  https://datashop.cboe.com/cboe-options-open-close-volume-summary
- Cboe Option EOD Summary: https://datashop.cboe.com/option-eod-summary
- OCC daily open interest:
  https://www.theocc.com/market-data/market-data-reports/other-market-data-info/batch-processing/daily-open-interest
- SEC/Investor.gov introduction to options and risk:
  https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-63
- FINRA warning on third-party auto-trading services:
  https://www.finra.org/investors/insights/auto-trading-unregistered-entities
