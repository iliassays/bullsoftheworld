# Reported Accumulation Near Yearly Low

## Status

Descriptive cross-evidence hypothesis. It is not a validated edge, strategy signal, trade
recommendation, Atlas urgency input, or paper-book admission rule.

## Research question

Which liquid securities are within 15% of their 52-week low while delayed ownership reports show
increasing institutional participation?

The intersection is useful because price location and reported ownership answer different
questions. It does not establish who traded, when they traded, why they traded, or whether the
security will reverse.

## Market policies

### DSE

- Completed-session close is 0% to 15% above the 52-week low.
- Reported institutional ownership category increased by at least 0.10 percentage points.
- The standard DSE visibility, category, capitalization, free-float, and liquidity gates apply.
- Rank by the reported category increase, then proximity to the low.

DSE data is a category percentage. It does not identify institutions or individual transactions.
The source stores the reporting period but does not currently store a trustworthy publication
timestamp. Historical strategy tests must therefore not pretend the report was known on its
period-end date.

### US

- Completed-session close is 0% to 15% above the 52-week low.
- At least five latest-quarter manager actions are present.
- Net manager breadth is at least +10%, where breadth is:
  `(new + increased - reduced - exited) / (new + increased + reduced + exited)`.
- Aggregate reported net shares are positive.
- The standard US visibility, capitalization, free-float, and liquidity gates apply.
- Rank by manager breadth, then proximity to the low.

Manager breadth is the primary participation measure because raw quarter-over-quarter share
percentages can be dominated by small prior denominators, new coverage, splits, and other corporate
actions. Form 13F remains delayed and excludes shorts, trade dates, execution prices, and intent.

## Product behavior

- Retail Ideas labels the board `utility`: a research shortlist with report-period and public-filing
  dates where available.
- Atlas may show the intersection as a cross-evidence observation.
- The observation does not change research urgency and cannot create an Agent Decision.
- Missing or insufficient evidence produces no clue rather than a guessed result.

## Promotion requirements

Before this hypothesis can influence a strategy or paper book:

1. Preserve point-in-time ownership availability, including DSE publication timestamps.
2. Include delisted/inactive securities and corporate-action-adjusted prices.
3. Preregister holding period, entry timing, costs, liquidity, benchmark, and rejection criteria.
4. Evaluate discovery, validation, and untouched holdout periods separately for each market.
5. Require stable excess return, drawdown, turnover, and capacity after costs.

Until those gates pass, the correct conclusion is `research clue only`.
