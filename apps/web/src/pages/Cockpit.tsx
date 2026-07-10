import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  api,
  type AgentDetail,
  type AgentSummary,
} from "../lib/api";
import { formatDhakaDateTime } from "../lib/time";
import { Spinner } from "../components/ui";

// Admin cockpit for the five agent model portfolios (English-only: internal tool, not a tenant
// surface). Read-only by design — the trading engine is the only writer; this page is for
// reviewing what it did and why (every trade carries its reason + the quote freshness it used).

const ADMIN_TOKEN_KEY = "bulls.adminToken";

const tk = (v: number | null | undefined, digits = 0) =>
  v == null
    ? "—"
    : `৳${v.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;

function pnlClass(v: number | null | undefined) {
  if (v == null || v === 0) return "text-muted";
  return v > 0 ? "text-up" : "text-down";
}

function TokenGate({ onSet }: { onSet: (t: string) => void }) {
  const [value, setValue] = useState("");
  return (
    <div className="max-w-sm mx-auto mt-16 bg-surface border border-border rounded-2xl p-6 text-center">
      <div className="text-3xl">🛸</div>
      <div className="font-bold mt-2">Cockpit</div>
      <p className="text-sm text-muted mt-1.5">
        Admin token required. It stays in this browser only.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (value.trim()) onSet(value.trim());
        }}
        className="mt-4 flex gap-2"
      >
        <input
          type="password"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="X-Admin-Token"
          className="flex-1 bg-card border border-border rounded-full px-4 py-2 text-sm"
        />
        <button
          type="submit"
          className="rounded-full px-5 py-2 text-sm font-bold bg-accent text-bg hover:opacity-90"
        >
          Enter
        </button>
      </form>
    </div>
  );
}

function HoldingsTable({ detail }: { detail: AgentDetail }) {
  if (!detail.holdings.length)
    return <div className="text-sm text-muted py-3">No open positions — all cash.</div>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm mt-2">
        <thead>
          <tr className="text-left text-[11px] uppercase text-muted">
            <th className="py-1 pr-3">Code</th>
            <th className="py-1 pr-3 text-right">Qty</th>
            <th className="py-1 pr-3 text-right">Sellable</th>
            <th className="py-1 pr-3 text-right">Avg cost</th>
            <th className="py-1 pr-3 text-right">LTP</th>
            <th className="py-1 pr-3 text-right">Value</th>
            <th className="py-1 text-right">P&L</th>
          </tr>
        </thead>
        <tbody>
          {detail.holdings.map((h) => (
            <tr key={h.code} className="border-t border-border">
              <td className="py-1.5 pr-3 font-semibold">{h.code}</td>
              <td className="py-1.5 pr-3 text-right">{h.quantity}</td>
              <td className="py-1.5 pr-3 text-right">
                {h.sellable_quantity < h.quantity ? (
                  <span title="Remainder still inside the T+2 settlement window">
                    {h.sellable_quantity}
                    <span className="text-muted"> / {h.quantity}</span>
                  </span>
                ) : (
                  h.quantity
                )}
              </td>
              <td className="py-1.5 pr-3 text-right">{h.avg_cost.toFixed(2)}</td>
              <td className="py-1.5 pr-3 text-right">{h.ltp?.toFixed(2) ?? "—"}</td>
              <td className="py-1.5 pr-3 text-right">{tk(h.value)}</td>
              <td className={`py-1.5 text-right font-semibold ${pnlClass(h.pnl_pct)}`}>
                {h.pnl_pct == null ? "—" : `${h.pnl_pct > 0 ? "+" : ""}${h.pnl_pct.toFixed(1)}%`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TradeLog({ detail }: { detail: AgentDetail }) {
  if (!detail.trades.length)
    return <div className="text-sm text-muted py-3">No trades yet.</div>;
  return (
    <div className="mt-2 space-y-2">
      {detail.trades.map((t) => (
        <div key={t.id} className="bg-card border border-border rounded-xl px-3 py-2 text-sm">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <span
              className={`text-[11px] font-bold uppercase ${t.side === "buy" ? "text-up" : "text-down"}`}
            >
              {t.side}
            </span>
            <span className="font-semibold">{t.code}</span>
            <span>
              {t.quantity} × {t.price.toFixed(2)}
            </span>
            <span className="text-muted">fee {t.fee.toFixed(2)}</span>
            <span className="text-muted ml-auto text-[11px]">
              {t.trade_date} · settles {t.settles_on}
              {t.side === "sell" && !t.settled && (
                <span className="text-accent"> · proceeds pending</span>
              )}
            </span>
          </div>
          <div className="text-muted mt-1">{t.reason}</div>
          <div className="text-[10px] text-muted mt-0.5">
            quote as of {formatDhakaDateTime(t.quote_as_of)}
          </div>
        </div>
      ))}
    </div>
  );
}

function AgentCard({ agent, token }: { agent: AgentSummary; token: string }) {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<AgentDetail | null>(null);

  useEffect(() => {
    if (!open || detail) return;
    api.adminAgentDetail(token, agent.handle).then(setDetail).catch(() => setDetail(null));
  }, [open, detail, token, agent.handle]);

  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full text-left"
      >
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="font-bold">{agent.display_name}</span>
          <span className="text-[11px] text-muted">@{agent.handle}</span>
          {!agent.is_active && (
            <span className="text-[11px] font-bold text-down uppercase">paused</span>
          )}
          <span className={`ml-auto font-bold ${pnlClass(agent.pnl)}`}>
            {agent.pnl == null
              ? "—"
              : `${agent.pnl > 0 ? "+" : ""}${tk(agent.pnl)} (${agent.pnl_pct?.toFixed(2)}%)`}
          </span>
        </div>
        <p className="text-xs text-muted mt-1">{agent.description}</p>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 mt-3 text-sm">
          <div>
            <div className="text-[10px] uppercase text-muted">Equity</div>
            <div className="font-semibold">{tk(agent.equity)}</div>
          </div>
          <div>
            <div className="text-[10px] uppercase text-muted">Cash</div>
            <div className="font-semibold">{tk(agent.cash_settled)}</div>
          </div>
          <div>
            <div className="text-[10px] uppercase text-muted">Settling</div>
            <div className="font-semibold">{tk(agent.cash_pending)}</div>
          </div>
          <div>
            <div className="text-[10px] uppercase text-muted">Positions</div>
            <div className="font-semibold">{agent.positions}</div>
          </div>
          <div>
            <div className="text-[10px] uppercase text-muted">Trades</div>
            <div className="font-semibold">{agent.trades_total}</div>
          </div>
        </div>
        {agent.quotes_as_of && (
          <div className="text-[10px] text-muted mt-2">
            valued at quotes as of {formatDhakaDateTime(agent.quotes_as_of)} (delayed)
          </div>
        )}
      </button>
      {open && (
        <div className="mt-3 border-t border-border pt-2">
          {detail ? (
            <>
              <div className="text-[11px] uppercase text-muted font-bold mt-1">Holdings</div>
              <HoldingsTable detail={detail} />
              <div className="text-[11px] uppercase text-muted font-bold mt-4">Trade log</div>
              <TradeLog detail={detail} />
            </>
          ) : (
            <Spinner />
          )}
        </div>
      )}
    </div>
  );
}

export function Cockpit() {
  const [token, setToken] = useState<string | null>(() =>
    sessionStorage.getItem(ADMIN_TOKEN_KEY),
  );
  const [agents, setAgents] = useState<AgentSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setError(null);
    api
      .adminAgents(token)
      .then((list) => {
        setAgents(list);
        setError(null); // a stale error from an earlier racing load must not outlive success
      })
      .catch((e: unknown) => {
        if (e instanceof ApiError && e.status === 403) {
          sessionStorage.removeItem(ADMIN_TOKEN_KEY);
          localStorage.removeItem(ADMIN_TOKEN_KEY);
          setToken(null);
        } else setError("Could not load agents — is the API up?");
      });
  }, [token]);

  useEffect(load, [load]);

  if (!token)
    return (
      <TokenGate
        onSet={(t) => {
          sessionStorage.setItem(ADMIN_TOKEN_KEY, t);
          localStorage.removeItem(ADMIN_TOKEN_KEY);
          setToken(t);
        }}
      />
    );

  const total = agents?.reduce((s, a) => s + (a.equity ?? 0), 0) ?? null;
  const invested = agents?.reduce((s, a) => s + a.initial_capital, 0) ?? null;

  return (
    <div className="space-y-3">
      <div className="flex items-baseline gap-3">
        <h1 className="text-lg font-bold">🛸 Cockpit — Agent Portfolios</h1>
        <button type="button" onClick={load} className="text-xs text-accent ml-auto">
          Refresh
        </button>
      </div>
      <p className="text-xs text-muted">
        Simulated ৳1,00,000 model portfolios run by deterministic strategy rules on the 15-minute
        quote cycle, with DSE T+2 settlement. Paper trading on delayed quotes — an internal
        experiment, not advice, and not visible to users.
      </p>
      {agents && total != null && invested != null && (
        <div className="bg-surface border border-border rounded-2xl p-4 flex flex-wrap gap-x-6 gap-y-1 text-sm">
          <span className="text-muted">All agents</span>
          <span className="font-bold">{tk(total)}</span>
          <span className={`font-bold ${pnlClass(total - invested)}`}>
            {total - invested >= 0 ? "+" : ""}
            {tk(total - invested)} vs {tk(invested)} deployed
          </span>
        </div>
      )}
      {error && <div className="text-sm text-down">{error}</div>}
      {!agents && !error && <Spinner />}
      {agents?.map((a) => <AgentCard key={a.handle} agent={a} token={token} />)}
      {agents && agents.length === 0 && (
        <div className="text-sm text-muted">
          No agent portfolios found — run <code>scripts/seed_agent_portfolios.py</code>.
        </div>
      )}
    </div>
  );
}
