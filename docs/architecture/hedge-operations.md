# Hedge research portal

## Runtime boundary

The Hedge web process is a read-only presentation service. HTTP requests may read the latest quote
book, agent executions, and the persisted EOD snapshot; they must not scan historical bars, compute
the daily buy list, run a backtest, or execute DDL.

The historical quality-reversal simulation runs in `bullsofdhaka-hedge-refresh.service`. Its timer
fires after the DSE EOD chain, with a low CPU quota and idle I/O priority. The job loads bars and
fundamentals once, computes the daily monitor publication, portfolio history, and signal ledger,
then writes the tenant-bound read models in one transaction:

- `hedge_track_record_snapshots`
- `hedge_daily_scan_snapshots`
- `hedge_signals`

All tables use forced PostgreSQL row-level security on `tenant_id`. The production runtime role has
DML privileges but no schema-creation privilege.

`hedge_daily_scan_snapshots` is the point-in-time archive. One insert-only row is published per DSE
session with exact new signals, still-open signal episodes, the current pre-trigger watchlist, and
added/continued/removed codes versus the prior publication. Its canonical JSON payload has a
SHA-256 fingerprint. Repeated refreshes reuse an already-published date instead of rewriting
historical evidence. There is deliberately no synthetic archive before deployment.

The latest publication is also copied into
`hedge_track_record_snapshots.payload.daily_scan` for compatibility. Home, Risk/Sizing, the archive
selector, and the signals API read the small publication documents; a cache miss never loads DSE
bars or fundamentals.

Hedge is a frozen legacy research system, not Atlas portfolio authority. Its daily screen does not
display a copied or hard-coded performance number. Older immutable publications may still contain
the former `track_record` object as historical payload evidence, but the compatibility projection
deliberately ignores it. The Legacy backtest page reads the current dynamic snapshot and labels its
same-close entry, fractional-unit, missing-slippage, missing-capacity, missing-settlement,
future-liquidity-filter and fiscal-year knowledge-time limitations. The signal-episode average is
also labelled as an overlapping-event statistic, not a shared-capital portfolio return.

## Agent portfolios

The agent engine is deterministic paper trading, not an LLM trader. Every intraday tick performs:

1. settlement of due sell proceeds;
2. exits against fresh delayed quotes;
3. ranked entries using remaining settled cash and position slots.

Portfolio rows are locked during a tick to prevent overlapping worker/manual runs from executing the
same decision twice. Queries are explicitly scoped by tenant, market, and user. The UI reconstructs
FIFO execution performance independently and reports realized P&L, unrealized P&L, fees, closed
trades, win rate, quote freshness, cash, pending settlement, and holdings.

Qualifying setups that cannot be purchased are stored in `agent_opportunities`. One row represents
one continuous episode, not one row per 15-minute tick. It records rank, signal explanation, settled
and pending cash, free slots, the executable cash threshold, observation counts, and the delayed
price path. An episode resolves as `entered` when the account later buys it or `expired` when the
strategy no longer qualifies it. Best/worst/since-missed returns are counterfactual observations,
not simulated fills or portfolio P&L.

`QualityReversalPortfolio` is the forward-only account for the exact archived Scheme-3 decision.
It reads only `new_signals` from the immediately preceding DSE trading session, ranks them by the
published conviction score, and executes through the same delayed-quote, brokerage, settlement,
cash, slot, circuit-lock, opportunity, and audit machinery as every other model portfolio. Policy:
10 positions, 10% target allocation per entry, -10% stop, +25% target, and a 63-trading-session time
exit. It never backfills historical fills; its performance starts when the account is provisioned.

This Hedge agent account is separate from Atlas. The production check on 18 July 2026 found no DSE
Atlas shadow portfolio and no execution in this Hedge account. An existing empty legacy account is
not permission to create an Atlas book or inherit the legacy backtest; any future Atlas book needs a
passed immutable admission report and an explicit inception date.

No strategy should be promoted from experimental status based on a few days of open-position
mark-to-market performance. Evaluation requires enough closed trades across more than one market
regime, comparison with DSEX, drawdown, turnover, and fee-aware returns.
