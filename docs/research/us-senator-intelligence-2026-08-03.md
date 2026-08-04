# US Senator Intelligence: research and implementation decision

Date: 2026-08-03  
Status: proposed evidence module; legal and data-license gate required before ingestion  
Market boundary: US only

## Decision

Senate transaction disclosures can add useful context to Atlas, but they are not a real-time
insider-trading feed and must not be presented as one. The initial product should be a
**Senator Intelligence** evidence module that answers:

1. What transaction was publicly disclosed, by whom, and for whose account?
2. When did the transaction occur, when was it filed, and when did Bulls first observe it?
3. How stale was the disclosure when it became actionable to the public?
4. Is the issuer connected to the senator's committee jurisdiction or current legislative work?
5. Did other senators, corporate insiders, institutions, catalysts, or market data corroborate it?
6. Historically, did similarly disclosed events add benchmark-relative value after publication?

It must not say that a senator "bought today" unless the transaction date is today. The primary
timestamp in any alert is the public disclosure timestamp; the historical transaction date is
shown separately.

## Material constraints

### Disclosure latency

The Senate Select Committee on Ethics states that a Periodic Transaction Report (PTR) is required
for a purchase, sale, or exchange over $1,000. It is due within 30 days after written notification,
but no later than 45 days after the transaction. The public therefore cannot consistently observe
the senator's entry in time to copy it.

The research event must be `first_public_at`, never `transaction_date`. A strategy may fill no
earlier than the next observable eligible market price after `first_public_at` or Bulls'
`first_seen_at`, whichever is later.

### Legal use restriction

The Senate eFD access page states that obtaining or using a financial disclosure report for a
commercial purpose is unlawful, except for qualifying news and communications media dissemination.
Bulls is intended to become a commercial research product. Direct eFD scraping and commercial use
therefore remain blocked until counsel provides a written basis.

An alternative is a vendor agreement that explicitly grants commercial use and the required display
or redistribution rights. A hobby or personal API subscription is not sufficient. For example,
Quiver's published pricing says its Hobbyist and Trader plans have no commercial-use rights; its
Commercial plan requires a quote.

### Evidence is mixed

The empirical literature does not justify treating all congressional trades as alpha. Belmont,
Sacerdote, Sehgal and Van Hoek (2022) report no aggregate evidence of superior post-STOCK-Act stock
selection. Chen and Sacerdote (2026) similarly find that congressional portfolios generally match
or underperform benchmarks and resemble public-signal-following. A recent working paper reports
some post-disclosure predictability, but this is not yet enough to bypass Bulls' own point-in-time
validation.

The module is therefore evidence and hypothesis generation first. It cannot create an Agent Decision
or paper target until a separately registered strategy passes temporal validation, costs, capacity,
and holdout gates.

## Source strategy

### Required transaction source

Use a provider adapter so licensing and provenance do not leak into domain logic.

Preferred production path:

- licensed structured congressional-trades vendor;
- Senate chamber filter;
- historical backfill plus amendment history;
- report/source URL retained for audit;
- contract explicitly permits commercial internal analytics and the intended customer display;
- service-level description for publication latency and corrections.

Candidate for commercial quotation: Quiver Congress Trades API. Its API documents transaction date,
report date, chamber, member, ticker, transaction type and disclosed range, and claims delivery as
reports are filed. These claims must be checked against a sample and written contract.

Do not use the Senate eFD portal directly in production until the legal gate closes. Do not use an
unlicensed community scraper as a production dependency.

### Legislative context source

Use the official Congress.gov API for member identity, sponsored and cosponsored legislation, bills,
actions, subjects, committees and committee meetings. It returns machine-readable JSON/XML, requires
a free API key, and currently permits 5,000 requests per hour. This source can update the context
graph independently of the transaction vendor.

### Existing Bulls evidence

Join the disclosure to existing US-only data:

- security master and historical ticker/CUSIP mappings;
- EOD and intraday prices;
- SEC filings and Company Facts;
- Forms 3/4/5, 13D/G, 13F and capital-structure events;
- FINRA short volume and short interest, kept semantically distinct;
- catalysts, government-contract evidence and company fundamentals.

No Senate data or derived feature may enter a DSE table, scan, cache key, job, API response or Atlas
workspace.

## Point-in-time data contract

### Core entities

`senate_people`

- stable Bioguide/member identifier, name, party, state and active dates;
- source version and first/last observed timestamps.

`senate_committee_memberships`

- person, committee/subcommittee, role, effective interval and source;
- immutable effective-dated history, not only current membership.

`senate_disclosure_reports`

- provider report ID, filer, report type, filed/public/first-seen timestamps;
- source URL, raw payload checksum, amendment/supersession relationship;
- provider and license metadata.

`senate_disclosure_transactions`

- report ID and stable row key;
- transaction date, owner (member/spouse/dependent/joint), type and asset description;
- disclosed amount lower/upper bounds, not a fabricated exact amount;
- raw ticker plus resolved security ID and mapping confidence;
- asset type, comment, first-seen timestamp and correction status.

`senate_legislative_events`

- bill/action/meeting/member/committee identifiers;
- event timestamp, subjects, issuer/industry mappings and mapping confidence;
- explicit source versus inferred relationship.

Every update is idempotent. Raw artifacts are immutable. Corrections append a new version and
supersede the prior version rather than rewriting history.

## Timely ingestion design

Polling cannot remove statutory disclosure delay. It can minimize Bulls' delay after publication.

- Prefer provider webhook or incremental cursor when contractually available.
- Otherwise poll every 15 minutes during 06:00-23:00 US Eastern and hourly overnight.
- Persist provider event time, `first_public_at`, `first_seen_at` and `ingested_at` separately.
- Perform a nightly 90-day reconciliation for amendments, deletions and late filings.
- Backfill by report/publication time and preserve each historical version.
- Deduplicate on provider ID plus normalized row fingerprint.
- Retry with bounded exponential backoff and a dead-letter queue.
- Health checks cover poll age, source lag, parse failures, unresolved symbols, duplicate rate,
  correction rate and raw-artifact retention.

The UI should state, for example:

> Disclosed 2 hours ago. Transaction occurred 23 days earlier. Purchase range $15,001-$50,000.

It must not show an artificial exact position size or exact execution price.

## Research features

Keep observable features separate from conclusions:

- disclosure lag in calendar and trading days;
- purchase, sale, exchange, option or other asset type;
- member versus spouse/dependent ownership;
- disclosed amount bucket and conservative lower-bound notional;
- new position versus repeat accumulation when inferable from prior disclosures;
- distinct-senator purchase/sale clusters over 5, 10 and 20 sessions;
- committee-jurisdiction relevance, with effective-dated membership;
- contemporaneous sponsored/cosponsored bill and committee-event relevance;
- historical post-publication behavior for this senator, shrunk toward the population mean;
- agreement or disagreement with Form 4 insiders, 13D/G, 13F, fundamentals and catalysts;
- liquidity, spread, volatility, market-cap and crowding controls;
- market and sector regime at publication.

Party affiliation is descriptive metadata, not a standalone alpha feature. Senator rankings require
minimum sample sizes, out-of-sample evaluation and empirical-Bayes shrinkage to prevent a few lucky
trades from becoming a leaderboard.

## Registered studies

Run studies from publication time using the next eligible open. Do not use transaction-date prices as
an achievable entry.

1. Individual-stock purchases versus matched sector/size/liquidity controls.
2. Sales as a risk/context event; do not initially model them as executable shorts.
3. Two-or-more distinct-senator purchase clusters.
4. Committee-relevant purchases versus non-relevant purchases.
5. Fast disclosures (0-7 days) versus medium (8-21), stale (22-45), and late (>45).
6. Purchases corroborated by Form 4, 13D/G, 13F, catalysts or demand signatures.
7. Member-owned versus spouse/dependent transactions.

Measure 1/5/10/20/60/120-session absolute and benchmark-relative returns, MFE, MAE, drawdown,
turnover, spread/slippage, capacity and delisting outcomes. Use walk-forward discovery,
validation and untouched holdout periods. Include amended and late reports exactly when Bulls would
have observed them.

## Product surface

Do not create a sensational "Senators are buying" board. Add the module only after licensing and
data-quality gates pass.

Ticker dossier:

- **Senate disclosures** timeline with transaction and disclosure dates;
- owner, type, amount range and source;
- legislative/committee relevance labeled `documented`, `mapped`, or `not established`;
- corroborating and contradictory evidence;
- post-publication return tracking, clearly separated from the senator's unknown execution return.

Atlas research inbox:

- new public disclosure;
- clustered purchase disclosures;
- committee/legislative relevance;
- correction or amendment;
- stale disclosure shown as context, not urgency.

Alerts are allowed only for newly public, successfully mapped, licensed records. An alert says
`new disclosure`, never `buy signal`.

## Promotion gates

1. Written commercial-use and display rights.
2. At least three years of point-in-time history, including amendments and delisted securities.
3. Sample audit against original reports with field-level precision/recall targets.
4. Reliable ticker/security resolution with an explicit unresolved state.
5. Publication-time backtest with realistic next-open execution.
6. Holdout evidence after costs and matched benchmarks.
7. Prospective shadow collection before any strategy eligibility.

Until all gates pass, Senator Intelligence remains an internal research dataset and cannot affect
Atlas conviction, position sizing or paper execution.

## Policy risk

Several active proposals would restrict or prohibit congressional stock trading. The architecture
must tolerate the transaction feed shrinking or ending. Legislative events, committee jurisdiction,
government contracts, lobbying and issuer political exposure remain useful even if member trading is
banned.

## Sources reviewed

- Senate Select Committee on Ethics, Financial Disclosure:
  https://www.ethics.senate.gov/public/index.cfm/financialdisclosure
- Senate eFD public access and statutory use notice:
  https://efdsearch.senate.gov/search/home/
- Library of Congress, Congress.gov API:
  https://github.com/LibraryOfCongress/api.congress.gov/
- Quiver Congress Trades API and pricing:
  https://api.quiverquant.com/datasets/congress-trades
  https://api.quiverquant.com/pricing/
- Belmont, Sacerdote, Sehgal and Van Hoek (2022), Journal of Public Economics:
  https://doi.org/10.1016/j.jpubeco.2022.104602
- Chen and Sacerdote (2026), NBER Working Paper 35041:
  https://www.nber.org/papers/w35041
- Pyun (2026), Congressional Trading, Informational Advantages, and Disclosure Timing:
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5295880

