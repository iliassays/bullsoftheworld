import { useCallback, useEffect, useState } from "react";
import {
  adminTokenStore,
  api,
  ApiError,
  type AdminOverview,
  type AdminTenant,
  type ModQueueItem,
} from "../lib/api";

// Ops cockpit — token-gated, tenant-scoped. English-only (internal tool). Route: /admin.

function Stat({ label, value, tone }: { label: string; value: string | number; tone?: string }) {
  return (
    <div className="rounded-2xl border border-border bg-card px-4 py-3">
      <div className="text-[11px] uppercase tracking-wide text-muted">{label}</div>
      <div className={`mt-1 text-2xl font-bold tnum ${tone ?? "text-text"}`}>{value}</div>
    </div>
  );
}

function fmt(ts: string | null): string {
  if (!ts) return "—";
  const d = new Date(ts);
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function TokenGate({ onAuthed }: { onAuthed: () => void }) {
  const [t, setT] = useState("");
  return (
    <div className="max-w-sm mx-auto mt-24 rounded-2xl border border-border bg-card p-6">
      <div className="text-lg font-bold mb-1">Admin</div>
      <p className="text-sm text-muted mb-4">Enter the admin token to open the ops console.</p>
      <input
        type="password"
        value={t}
        onChange={(e) => setT(e.target.value)}
        placeholder="X-Admin-Token"
        className="w-full rounded-xl bg-surface border border-border px-3 py-2 text-sm"
      />
      <button
        onClick={() => {
          if (t.trim()) {
            adminTokenStore.set(t.trim());
            onAuthed();
          }
        }}
        className="mt-3 w-full rounded-xl bg-accent text-black font-semibold py-2 text-sm"
      >
        Unlock
      </button>
    </div>
  );
}

export function Admin() {
  const [authed, setAuthed] = useState(!!adminTokenStore.get());
  const [tenants, setTenants] = useState<AdminTenant[]>([]);
  const [tenant, setTenant] = useState("");
  const [ov, setOv] = useState<AdminOverview | null>(null);
  const [queue, setQueue] = useState<ModQueueItem[]>([]);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  const fail = useCallback((e: unknown) => {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) {
      adminTokenStore.clear();
      setAuthed(false);
      setErr("Invalid admin token.");
    } else {
      setErr(e instanceof ApiError ? e.detail : "Something went wrong.");
    }
  }, []);

  useEffect(() => {
    if (!authed) return;
    api
      .adminTenants()
      .then((ts) => {
        setTenants(ts);
        setTenant((cur) => cur || ts[0]?.name || "");
      })
      .catch(fail);
  }, [authed, fail]);

  const load = useCallback(async () => {
    if (!tenant) return;
    setLoading(true);
    setErr("");
    try {
      const [o, q] = await Promise.all([api.adminOverview(tenant), api.modQueue("pending")]);
      setOv(o);
      setQueue(q.items);
    } catch (e) {
      fail(e);
    } finally {
      setLoading(false);
    }
  }, [tenant, fail]);

  useEffect(() => {
    if (authed && tenant) load();
  }, [authed, tenant, load]);

  async function act(id: number, kind: "approve" | "block") {
    try {
      await (kind === "approve" ? api.modApprove(id) : api.modBlock(id));
      await load();
    } catch (e) {
      fail(e);
    }
  }

  if (!authed) return <TokenGate onAuthed={() => setAuthed(true)} />;

  const m = ov?.moderation ?? {};
  return (
    <div className="max-w-[900px] mx-auto px-4 py-6">
      <div className="flex items-center gap-3 mb-5">
        <div className="text-xl font-bold">Admin console</div>
        <select
          value={tenant}
          onChange={(e) => setTenant(e.target.value)}
          className="rounded-full bg-surface border border-border px-3 py-1.5 text-sm"
        >
          {tenants.map((t) => (
            <option key={t.name} value={t.name}>
              {t.display_name} · {t.market}
            </option>
          ))}
        </select>
        <button onClick={load} className="text-xs text-muted hover:text-accent">
          ↻ refresh
        </button>
        <button
          onClick={() => {
            adminTokenStore.clear();
            setAuthed(false);
          }}
          className="ml-auto text-xs text-muted hover:text-down"
        >
          lock
        </button>
      </div>

      {err && <div className="mb-4 rounded-xl border border-down/40 bg-down/10 text-down text-sm px-3 py-2">{err}</div>}
      {loading && !ov && <div className="text-muted text-sm">Loading…</div>}

      {ov && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
            <Stat label="Users" value={ov.users} />
            <Stat label="Posts (total)" value={ov.posts_total} />
            <Stat label="Posts today" value={ov.posts_today} />
            <Stat
              label="Review pending"
              value={ov.review_pending}
              tone={ov.review_pending ? "text-accent" : "text-text"}
            />
            <Stat label="Agent notes" value={ov.agent_notes} />
            <Stat label="Reactions (7d)" value={ov.reactions_7d} />
            <Stat label="Blocked" value={m.blocked ?? 0} tone={(m.blocked ?? 0) ? "text-down" : "text-text"} />
            <Stat label="Flagged (24h)" value={ov.flagged_24h} />
          </div>

          {/* data-pipeline health */}
          <div className="rounded-2xl border border-border bg-card px-4 py-3 mb-4 grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
            <div>
              <div className="text-[11px] uppercase tracking-wide text-muted">Last EOD</div>
              <div className="font-semibold">{ov.last_eod_date ?? "—"}</div>
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-wide text-muted">Latest quote</div>
              <div className="font-semibold">{fmt(ov.latest_quote_as_of)}</div>
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-wide text-muted">Symbols active</div>
              <div className="font-semibold">{ov.symbols_active}</div>
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-wide text-muted">Symbols hidden</div>
              <div className="font-semibold">{ov.symbols_hidden}</div>
            </div>
          </div>

          {/* moderation review queue */}
          <div className="mb-4">
            <div className="text-sm font-bold mb-2">
              Review queue <span className="text-muted font-normal">({queue.length} pending)</span>
            </div>
            {queue.length === 0 ? (
              <div className="text-muted text-sm rounded-2xl border border-border bg-card px-4 py-6 text-center">
                Nothing waiting. 🎉
              </div>
            ) : (
              <div className="space-y-2">
                {queue.map((it) => (
                  <div key={it.post_id} className="rounded-2xl border border-border bg-card px-4 py-3">
                    <div className="flex items-center gap-2 text-xs text-muted mb-1">
                      <span className="font-semibold text-text">@{it.author_handle}</span>
                      {it.account_age_days != null && <span>· {it.account_age_days}d old</span>}
                      {it.reason && (
                        <span className="rounded-full bg-accent/15 text-accent px-2 py-0.5">{it.reason}</span>
                      )}
                      {it.risk_score != null && <span>· risk {it.risk_score.toFixed(2)}</span>}
                      {it.cashtags.map((c) => (
                        <span key={c} className="text-muted">${c}</span>
                      ))}
                    </div>
                    <div className="text-sm text-text mb-2">{it.body}</div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => act(it.post_id, "approve")}
                        className="rounded-lg bg-up/15 text-up text-xs font-semibold px-3 py-1.5"
                      >
                        Approve
                      </button>
                      <button
                        onClick={() => act(it.post_id, "block")}
                        className="rounded-lg bg-down/15 text-down text-xs font-semibold px-3 py-1.5"
                      >
                        Block
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* recent moderation events + top cashtags */}
          <div className="grid sm:grid-cols-2 gap-4">
            <div className="rounded-2xl border border-border bg-card px-4 py-3">
              <div className="text-sm font-bold mb-2">Recent flags</div>
              {ov.recent_events.length === 0 ? (
                <div className="text-muted text-sm">No flags yet.</div>
              ) : (
                <ul className="space-y-1.5 text-xs">
                  {ov.recent_events.map((e, i) => (
                    <li key={i} className="flex items-center gap-2">
                      <span
                        className={`rounded px-1.5 py-0.5 font-semibold ${
                          e.decision === "block" ? "bg-down/15 text-down" : "bg-accent/15 text-accent"
                        }`}
                      >
                        {e.decision}
                      </span>
                      <span className="text-muted">L{e.layer}</span>
                      <span className="text-text">{e.reason_code ?? e.categories.join(",")}</span>
                      <span className="ml-auto text-muted">#{e.post_id}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="rounded-2xl border border-border bg-card px-4 py-3">
              <div className="text-sm font-bold mb-2">Top cashtags (7d)</div>
              {ov.top_cashtags.length === 0 ? (
                <div className="text-muted text-sm">No tagged posts yet.</div>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {ov.top_cashtags.map((c) => (
                    <span key={c.code} className="rounded-full bg-surface border border-border px-2.5 py-1 text-xs">
                      <span className="font-semibold">${c.code}</span>{" "}
                      <span className="text-muted">{c.posts}</span>
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="mt-4 text-[11px] text-muted">
            {ov.tenant} · {ov.market} · generated {fmt(ov.generated_at)}
          </div>
        </>
      )}
    </div>
  );
}
