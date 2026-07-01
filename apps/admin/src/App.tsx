import { useCallback, useEffect, useState } from "react";
import {
  adminTokenStore,
  api,
  ApiError,
  type AdminOverview,
  type AdminTenant,
  type ModQueueItem,
} from "./lib/api";

function fmt(ts: string | null): string {
  if (!ts) return "—";
  return new Date(ts).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function Stat({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string | number;
  hint?: string;
  tone?: string;
}) {
  return (
    <div className="rounded-2xl border border-border bg-card px-4 py-3">
      <div className="text-[11px] uppercase tracking-wide text-muted">{label}</div>
      <div className={`mt-1 text-2xl font-bold tnum ${tone ?? "text-text"}`}>{value}</div>
      {hint && <div className="mt-0.5 text-[11px] text-muted leading-tight">{hint}</div>}
    </div>
  );
}

function TokenGate({ onAuthed }: { onAuthed: () => void }) {
  const [t, setT] = useState("");
  const [err, setErr] = useState("");
  async function unlock() {
    if (!t.trim()) return;
    adminTokenStore.set(t.trim());
    try {
      await api.tenants(); // validate the token before entering
      onAuthed();
    } catch (e) {
      adminTokenStore.clear();
      setErr(e instanceof ApiError && e.status === 403 ? "Invalid token." : "Could not reach the API.");
    }
  }
  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="w-80 rounded-2xl border border-border bg-card p-6">
        <div className="flex items-center gap-2 text-lg font-bold mb-1">🐂 Bulls Cockpit</div>
        <p className="text-sm text-muted mb-4">Ops console — enter the admin token.</p>
        <input
          type="password"
          value={t}
          onChange={(e) => setT(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && unlock()}
          placeholder="X-Admin-Token"
          className="w-full rounded-xl bg-surface border border-border px-3 py-2 text-sm"
        />
        {err && <p className="text-down text-xs mt-2">{err}</p>}
        <button onClick={unlock} className="mt-3 w-full rounded-xl bg-accent text-black font-semibold py-2 text-sm">
          Unlock
        </button>
      </div>
    </div>
  );
}

export function App() {
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
    } else {
      setErr(e instanceof ApiError ? e.detail : "Something went wrong.");
    }
  }, []);

  useEffect(() => {
    if (!authed) return;
    api
      .tenants()
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
      const [o, q] = await Promise.all([api.overview(tenant), api.modQueue("pending")]);
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
    <div className="flex h-screen">
      {/* sidebar */}
      <aside className="w-56 shrink-0 border-r border-border bg-surface flex flex-col p-4">
        <div className="flex items-center gap-2 font-bold text-base mb-6">🐂 Cockpit</div>
        <label className="text-[11px] uppercase tracking-wide text-muted mb-1">Tenant</label>
        <select
          value={tenant}
          onChange={(e) => setTenant(e.target.value)}
          className="rounded-xl bg-card border border-border px-3 py-2 text-sm mb-4"
        >
          {tenants.map((t) => (
            <option key={t.name} value={t.name}>
              {t.display_name} · {t.market}
            </option>
          ))}
        </select>
        <button
          onClick={load}
          className="rounded-xl border border-border text-sm py-2 hover:border-accent hover:text-accent transition"
        >
          ↻ Refresh
        </button>
        <div className="mt-auto pt-4 text-[11px] text-muted">
          {ov && <div className="mb-2">Updated {fmt(ov.generated_at)}</div>}
          <button
            onClick={() => {
              adminTokenStore.clear();
              setAuthed(false);
              setOv(null);
            }}
            className="text-muted hover:text-down"
          >
            🔒 Lock console
          </button>
        </div>
      </aside>

      {/* main */}
      <main className="flex-1 overflow-y-auto p-6">
        <div className="max-w-[1100px] mx-auto">
          <h1 className="text-xl font-bold mb-1">System overview</h1>
          <p className="text-sm text-muted mb-5">
            {ov ? `${ov.tenant} · ${ov.market}` : "Loading…"}
          </p>

          {err && (
            <div className="mb-4 rounded-xl border border-down/40 bg-down/10 text-down text-sm px-3 py-2">{err}</div>
          )}

          {ov && (
            <>
              <div className="text-[11px] uppercase tracking-wide text-muted mb-2">People &amp; content</div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                <Stat label="People" value={ov.users_people} hint="real signed-up accounts" />
                <Stat label="Official desks" value={ov.users_desks} hint="automated agent accounts" />
                <Stat label="User posts" value={ov.user_posts} hint="written by people (all time)" />
                <Stat label="Agent notes" value={ov.agent_notes} hint="posted by desks (all time)" />
                <Stat label="People posts today" value={ov.people_posts_today} hint={`published today · ${ov.market} time`} />
                <Stat label="Agent notes today" value={ov.agent_notes_today} hint={`published today · ${ov.market} time`} />
                <Stat label="Reactions (7d)" value={ov.reactions_7d} hint="agree/disagree, last 7 days" />
                <Stat
                  label="Review pending"
                  value={ov.review_pending}
                  hint="posts awaiting your approve/block"
                  tone={ov.review_pending ? "text-accent" : "text-text"}
                />
              </div>
              <div className="text-[11px] uppercase tracking-wide text-muted mb-2">Moderation</div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                <Stat label="Published" value={m.published ?? 0} hint="live in the feed" />
                <Stat label="Pending" value={m.pending ?? 0} hint="held at write, awaiting review" tone={(m.pending ?? 0) ? "text-accent" : "text-text"} />
                <Stat label="Blocked" value={m.blocked ?? 0} hint="rejected posts" tone={(m.blocked ?? 0) ? "text-down" : "text-text"} />
                <Stat label="Flagged (24h)" value={ov.flagged_24h} hint="held/blocked in last 24h" />
              </div>

              <div className="rounded-2xl border border-border bg-card px-4 py-3 mb-6 grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
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

              <div className="grid lg:grid-cols-[1.4fr_1fr] gap-6">
                {/* review queue */}
                <section>
                  <h2 className="text-sm font-bold mb-2">
                    Review queue <span className="text-muted font-normal">({queue.length} pending)</span>
                  </h2>
                  {queue.length === 0 ? (
                    <div className="text-muted text-sm rounded-2xl border border-border bg-card px-4 py-8 text-center">
                      Nothing waiting. 🎉
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {queue.map((it) => (
                        <div key={it.post_id} className="rounded-2xl border border-border bg-card px-4 py-3">
                          <div className="flex flex-wrap items-center gap-2 text-xs text-muted mb-1">
                            <span className="font-semibold text-text">@{it.author_handle}</span>
                            {it.account_age_days != null && <span>· {it.account_age_days}d old</span>}
                            {it.reason && (
                              <span className="rounded-full bg-accent/15 text-accent px-2 py-0.5">{it.reason}</span>
                            )}
                            {it.risk_score != null && <span>· risk {it.risk_score.toFixed(2)}</span>}
                            {it.cashtags.map((c) => (
                              <span key={c}>${c}</span>
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
                </section>

                {/* side panel */}
                <div className="space-y-4">
                  <section className="rounded-2xl border border-border bg-card px-4 py-3">
                    <h2 className="text-sm font-bold mb-2">Recent flags</h2>
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
                            <span className="text-text truncate">{e.reason_code ?? e.categories.join(",")}</span>
                            <span className="ml-auto text-muted">#{e.post_id}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </section>
                  <section className="rounded-2xl border border-border bg-card px-4 py-3">
                    <h2 className="text-sm font-bold mb-2">Top cashtags (7d)</h2>
                    {ov.top_cashtags.length === 0 ? (
                      <div className="text-muted text-sm">No tagged posts yet.</div>
                    ) : (
                      <div className="flex flex-wrap gap-2">
                        {ov.top_cashtags.map((c) => (
                          <span key={c.code} className="rounded-full bg-surface border border-border px-2.5 py-1 text-xs">
                            <span className="font-semibold">${c.code}</span> <span className="text-muted">{c.posts}</span>
                          </span>
                        ))}
                      </div>
                    )}
                  </section>
                </div>
              </div>
            </>
          )}
          {loading && !ov && <div className="text-muted text-sm">Loading…</div>}
        </div>
      </main>
    </div>
  );
}
