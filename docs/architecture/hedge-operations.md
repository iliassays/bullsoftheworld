# Hedge research portal

## Runtime boundary

The Hedge web process is a read-only presentation service. HTTP requests may read the latest quote
book, agent executions, and the persisted track-record snapshot; they must not scan multi-year bars,
run a backtest, or execute DDL.

The historical quality-reversal simulation runs in `bullsofdhaka-hedge-refresh.service`. Its timer
fires after the DSE EOD chain, with a low CPU quota and idle I/O priority. The job loads bars and
fundamentals once, computes the portfolio history and signal ledger, then replaces both tenant-bound
read models in one transaction:

- `hedge_track_record_snapshots`
- `hedge_signals`

Both tables use forced PostgreSQL row-level security on `tenant_id`. The production runtime role has
DML privileges but no schema-creation privilege.

## Agent portfolios

The agent engine is deterministic paper trading, not an LLM trader. Every intraday tick performs:

1. settlement of due sell proceeds;
2. exits against fresh delayed quotes;
3. ranked entries using remaining settled cash and position slots.

Portfolio rows are locked during a tick to prevent overlapping worker/manual runs from executing the
same decision twice. Queries are explicitly scoped by tenant, market, and user. The UI reconstructs
FIFO execution performance independently and reports realized P&L, unrealized P&L, fees, closed
trades, win rate, quote freshness, cash, pending settlement, and holdings.

No strategy should be promoted from experimental status based on a few days of open-position
mark-to-market performance. Evaluation requires enough closed trades across more than one market
regime, comparison with DSEX, drawdown, turnover, and fee-aware returns.
