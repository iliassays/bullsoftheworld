# Ideas, Markets, and Symbol research audit — 2026-07-12

This audit supersedes the decision-surface portions of `feature-audit-2026-07.md`. It reviews the
current multi-tenant implementation as a product, quantitative, data-contract, and retail-UX system.

## Executive verdict

The system is production-oriented, not a hobby implementation: calculations are deterministic,
analytics are precomputed, market capabilities are tenant-configured, evidence classes are explicit,
missing data is normally omitted, and the core suite has broad coverage. The main risks were not
basic engineering quality. They were **snapshot consistency**, **proxy language that sounded like
observed fund flow**, **heuristic scores presented beside broader checks as though they shared one
denominator**, and **test-data isolation**. The critical instances found in this audit were fixed.

The product is useful for a retail research workflow when read in this order:

1. **Ideas** answers what deserves investigation after the latest completed session.
2. **Markets** explains breadth, leadership, liquidity, ownership, valuation, and technical context.
3. **Symbol** supports the actual decision with chart, official evidence, fundamentals, ownership,
   liquidity, risks, and a pre-trade checklist.

It must not promise that users will earn. These tools can reduce research time, expose risk, and make
evidence traceable; they cannot create confidence that a security will produce a profit.

## Audit standard

Every visible claim was tested against four gates:

| Gate | Required behavior |
|---|---|
| Data clock | One stated snapshot per calculation, or both clocks explicitly labelled |
| Formula | Standard definition, valid denominator, no fabricated value from missing data |
| Evidence | Backtest/framework/utility wording matches what was actually validated |
| Retail action | A user can tell what the value means, what it does not prove, and what to check next |

## Ideas inventory

| Board | Calculation / evidence | Retail verdict |
|---|---|---|
| DSE Quality Reversal | >=40% below 52W high, near low, ROE>0, P/E 0–25, liquidity/cap gates, fresh 5-day-high break; locally backtested and regime-sensitive | Keep as flagship, with current bear-regime caution |
| DSE Oversold Quality | RSI<=30 plus profitability, valuation, liquidity, and cap gates; local factor evidence | Keep; correctly says zone, not timing signal |
| DSE Unusual Session Activity | completed-session volume/turnover anomaly against own history | Keep; activity only, no direction claim |
| DSE Value + Quality | P/E <0.8x sector median, ROE>=15, liquidity and cap gates | Keep; requires debt/EPS/news review |
| DSE Dividend Quality | trailing cash yield, positive EPS, liquidity/cap gates, now capped at 15% for the curated list | Keep; raw higher yield remains visible with caution elsewhere |
| US Relative Strength | session-close return relative to SPY | Keep as utility, not alpha claim |
| US Unusual Volume | completed-session relative volume | Keep as utility |
| US Recent Filings | recent normalized SEC filing evidence | Keep; filing is a catalyst candidate, not direction |
| US Cash-flow Quality | positive profit and free-cash-flow margins from SEC facts | Keep; sector comparability still matters |
| US Financial Risk | explicit balance-sheet/cash-flow flags; financial sectors excluded from generic leverage rules | Keep |
| 13F Accumulation / Distribution | quarter-over-quarter aggregate reported long-share change | Keep only with public-date, manager breadth, and disclosure limits |
| Watchlist filter | same boards restricted to user holdings/watchlist | Keep; high retention value |

All Ideas candidates are now restricted to the latest analytics date. A stale ticker row cannot rank
beside current-session rows. Empty boards remain visible as disciplined “no match” states.

## Markets inventory

### Market context

| Feature | Validation | Verdict |
|---|---|---|
| Market Pulse | latest market summary, turnover vs prior 20 sessions, quote breadth, sector leaders, explicit coverage ratio, deterministic risk mode | Keep; mixed EOD/quote clocks are labelled |
| Watch Today | nightly anomaly rank, completed-session change/reasons, EOD ADTV and 5% order-size guide | Keep; no live-price promise |
| Earnings week | official scheduled dates only; no inferred date | Keep |
| Sector heat | average quote change plus advancer/decliner breadth | Keep; equal-weight sector context, not sector-index return |
| Freshness contract | actual analysis date, expected date, quote time, next scheduled refresh, stale state | Essential; do not weaken |

### Reference screens

| Family | Included screens | Validation / decision |
|---|---|---|
| Price structure | near support, near resistance, near 52W high/low | Valid confirmed-pivot/range facts; framework only |
| Momentum | RSI oversold/overbought, above 200-DMA, 12–1 momentum, beating benchmark | Standard formulas; useful context, not entry timing |
| Activity | gainers, losers, most active, 1D/5D/1M unusual volume | Valid; up/down volume does not identify buyers or sellers |
| Price-volume proxy | positive/negative CMF, quiet CMF+OBV divergence | Keep after terminology fix; OHLCV cannot prove money or institutions moved |
| Value / quality | sector-relative P/E, EPS growth, ROE, trailing dividend yield | Keep; negative-base EPS growth is now omitted, high yields are flagged |
| Stability | annualized realized volatility | Keep; smoother history does not mean higher expected return |
| DSE ownership | foreign/institutional increases, institutional/sponsor reductions | High retail value; disclosure snapshots, not actual trade flow |
| US ownership | 13F aggregate increase/reduction | High research value; delayed and incomplete by construction |
| Community | watched, discussed, attention rising | Keep as attention data; never evidence of business quality |
| Chart patterns | flat base plus seven pivot-geometry patterns | Keep in advanced view; framework/experimental evidence must remain visible |

The `/screens` page date previously came from an unordered `LIMIT 1`; it now uses the maximum
analytics date, and cache version `v13` invalidates the incorrect labels. Screen membership is also
pinned to that date.

## Symbol page inventory

| Surface | Data and calculation | Retail verdict |
|---|---|---|
| Header quote | latest tenant-resolved delayed quote with timestamp | Keep; clear primary anchor |
| Quick stats | EOD market cap/P-E/EPS/free float plus quote volume | Keep; volume now says it is compared with a full-session 20-session average |
| 52-week range | latest price position between rolling low/high | Keep |
| Candlestick chart | daily OHLCV, EMA9/20, 20-day rolling volume-weighted average, confirmed pivots and pattern overlay | Keep; “VWAP” mislabel corrected |
| Plain Read | deterministic synthesis of size, liquidity, trend, volatility, ROE, value, dividend, CMF, disclosed ownership, RSI | Keep; high-ROE no longer means “high quality,” CMF is a proxy |
| Research brief | question-specific retrieval over official, signal, market, and community evidence with citations and evidence quality | Keep; retrieval supports evidence discovery, not numeric truth already in SQL |
| Key Levels | confirmed pivots, RSI zone, completed-session volume, optional delayed-price bridge | Keep; language now says technicians “often call,” not that a breakout is proven |
| Pre-trade checklist | news, trend, exit liquidity, invalidation, position size | Keep; now bilingual and market-neutral |
| Factor Scorecard | independent Trend/Quality/Value/Income/Momentum 0–10 dimensions with raw input and benchmark | Keep; no composite score |
| Investor Lens | six deterministic style reads with core score plus extended checks | Keep, but as drill-down; core vs extended checks now explicitly separated |
| Technicals | RSI, relative full-session volume, support/resistance, 52W position | Keep; largely overlaps Lens, so do not promote above it |
| News | decoded official events, materiality, dates, source links | Essential for DSE; SEC evidence should remain filing-native for US |
| Fundamentals | valuation, sector comparison, annual/quarterly history, SEC facts, dividends | Essential; valuation now carries its source close date and help is tenant-aware |
| DSE ownership | reconciled monthly composition, deltas, history, integrity total | Essential differentiator; neutral visual tone is correct |
| US institutional holdings | 13F dates, managers, changes, public-date returns, SPY excess, histories, limitations | Essential research tool; ownership direction is now visually neutral |
| Community | top discussion, feed, composer | Keep as separate evidence class; moderation remains mandatory |

## Correctness changes made in this audit

1. Removed delayed intraday quote input from EOD Investor Lens and Scorecard calculations; both use
   the latest completed-session close change.
2. Reused the shared technical scorer inside Investor Lens; removed duplicated scoring logic.
3. Stopped the frontend from generating a competing lens verdict from check rows.
4. Separated core scores from extended checks in the UI.
5. Omitted EPS growth when prior EPS is zero or negative; turnaround is not percentage growth.
6. Corrected the 13F 30/60-session return off-by-one.
7. Corrected rolling daily “VWAP” to “20D volume-weighted average.”
8. Replaced CMF inflow/buyer-control claims with accurate price-volume-proxy language.
9. Preserved high trailing dividend yields as facts, added explicit caution, and excluded >15% from
   the curated Dividend Quality board.
10. Fixed unordered Markets freshness date and restricted Ideas/Markets universes to the latest
    analytics date.
11. Added market-aware fundamental help and DSE Bangla financial labels.
12. Replaced infinite loaders with explicit unavailable states and guarded ticker requests against
    stale async responses.
13. Fixed a Scanner React key warning.
14. Changed DB ownership tests from committed fixtures to transaction-scoped fixtures and removed
    20 confirmed synthetic test symbols from the local application database.

## UX and product priorities

### Keep prominent

- Freshness and stale-data banners
- Ideas as the curated “start here” route
- Official news/SEC evidence before interpretation
- Liquidity, ADTV, free float, and order-size context
- Ownership changes with exact disclosure dates
- Factor inputs and benchmarks, not unexplained overall scores

### Keep secondary

- Full Markets board catalog
- Classic chart patterns without local edge
- Investor personas and technical details
- Community attention metrics until community depth is meaningful

### Do not add

- A single buy/sell score
- Price targets generated from these heuristics
- “Smart money is buying” from CMF/OBV
- Real-time language on completed-session screens
- Green/red ownership direction as a quality verdict

## Residual risks and next work

1. **US runtime certification is blocked locally:** 11,039 US symbols are `reference_only`; none are
   `ready`. Code and unit contracts pass, but real US Ideas/Markets/ticker output needs a ready cohort
   before sign-off.
2. **Operational freshness is currently delayed in the local data:** analytics latest is 2026-07-09
   while expected is 2026-07-12; MarketSummary is older. The UI now tells the truth, but ingestion and
   watchdog operations still need restoration/verification in the deployment environment.
3. **Desktop information density:** the UI is intentionally mobile-first and remains a narrow column
   on wide displays. Retail mobile is strong; institutional/desktop research should eventually use a
   wider, two-column symbol layout without changing the mobile hierarchy.
4. **Heuristic calibration:** score thresholds are transparent and deterministic but not a validated
   forecasting model. Track forward outcomes and calibration by market before changing evidence labels.
5. **Sector comparability:** ROE, P/E, leverage, and cash-flow rules need sector-specific treatment for
   banks, insurers, REITs, and pre-revenue companies as US coverage expands.

## Verification record

- Full Python suite: **435 passed, 37 skipped**
- Focused correctness suite: passed
- Ruff on touched Python modules: passed
- Production web TypeScript/Vite build: passed
- Browser QA: DSE Ideas, Markets, ticker Overview/Lens/Financials/Ownership at 390×844 and ticker Lens
  at 1280×900; no horizontal overflow; corrected freshness/labels observed
- Local DB fixture audit: 20 synthetic `T[0-9A-F]{8}` test symbols removed; count verified as zero
