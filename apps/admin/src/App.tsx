import { useCallback, useEffect, useState } from "react";
import { Bars } from "./components/Bars";
import {
  adminTokenStore,
  api,
  ApiError,
  type AdminOverview,
  type AdminTenant,
  type Analytics,
  type ModQueueItem,
} from "./lib/api";

function fmt(ts: string | null): string {
  if (!ts) return "—";
  return new Date(ts).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function Kpi({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string | number;
  sub?: string;
  tone?: string;
}) {
  return (
    <div className="rounded-2xl border border-border bg-card px-4 py-3">
      <div className="text-[11px] uppercase tracking-wide text-muted">{label}</div>
      <div className={`mt-1 text-2xl font-bold tnum ${tone ?? "text-text"}`}>{value}</div>
      {sub && <div className="mt-0.5 text-[11px] text-muted leading-tight">{sub}</div>}
    </div>
  );
}

function Panel({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-border bg-card px-4 py-3">
      <div className="flex items-baseline justify-between mb-2">
        <h2 className="text-sm font-bold">{title}</h2>
        {note && <span className="text-[11px] text-muted">{note}</span>}
      </div>
      {children}
    </section>
  );
}

function TokenGate({ onAuthed }: { onAuthed: () => void }) {
  const [t, setT] = useState("");
  const [err, setErr] = useState("");
  async function unlock() {
    if (!t.trim()) return;
    adminTokenStore.set(t.trim());
    try {
      await api.tenants();
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

const RANGES = [14, 30, 90];

export function App() {
  const [authed, setAuthed] = useState(!!adminTokenStore.get());
  const [tenants, setTenants] = useState<AdminTenant[]>([]);
  const [tenant, setTenant] = useState("");
  const [days, setDays] = useState(30);
  const [ov, setOv] = useState<AdminOverview | null>(null);
  const [an, setAn] = useState<Analytics | null>(null);
  const [queue, setQueue] = useState<ModQueueItem[]>([]);
  const [err, setErr] = useState("");

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
    setErr("");
    try {
      const [o, a, q] = await Promise.all([
        api.overview(tenant),
        api.analytics(tenant, days),
        api.modQueue(tenant, "pending"),
      ]);
      setOv(o);
      setAn(a);
      setQueue(q.items);
    } catch (e) {
      fail(e);
    }
  }, [tenant, days, fail]);

  useEffect(() => {
    if (authed && tenant) load();
  }, [authed, tenant, load]);

  async function act(id: number, kind: "approve" | "block") {
    try {
      await (kind === "approve" ? api.modApprove(tenant, id) : api.modBlock(tenant, id));
      await load();
    } catch (e) {
      fail(e);
    }
  }

  async function updateLead(id: number, status: string) {
    try {
      await api.institutionalLeadStatus(tenant, id, status);
      await load();
    } catch (e) {
      fail(e);
    }
  }

  async function updateFeedback(id: number, status: string) {
    try {
      await api.betaFeedbackStatus(tenant, id, status);
      await load();
    } catch (e) {
      fail(e);
    }
  }

  if (!authed) return <TokenGate onAuthed={() => setAuthed(true)} />;

  const k = an?.kpis;
  const m = ov?.moderation ?? {};
  return (
    <div className="flex h-screen">
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
              setAn(null);
            }}
            className="text-muted hover:text-down"
          >
            🔒 Lock console
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto p-6">
        <div className="max-w-[1100px] mx-auto">
          <div className="flex items-center justify-between mb-1">
            <h1 className="text-xl font-bold">Analytics</h1>
            <div className="flex rounded-full border border-border overflow-hidden text-xs">
              {RANGES.map((r) => (
                <button
                  key={r}
                  onClick={() => setDays(r)}
                  className={`px-3 py-1 ${days === r ? "bg-accent text-black font-semibold" : "text-muted"}`}
                >
                  {r}d
                </button>
              ))}
            </div>
          </div>
          <p className="text-sm text-muted mb-5">{ov ? `${ov.tenant} · ${ov.market}` : "Loading…"}</p>

          {err && (
            <div className="mb-4 rounded-xl border border-down/40 bg-down/10 text-down text-sm px-3 py-2">{err}</div>
          )}

          {k && (
            <>
              {/* growth KPIs */}
              <div className="text-[11px] uppercase tracking-wide text-muted mb-2">Registered users</div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
                <Kpi label="People" value={k.people_total} sub={`+${k.new_people_7d} in 7d · +${k.new_people_30d} in 30d`} />
                <Kpi label="Active (7d)" value={k.active_people_7d} sub="posted or reacted" tone="text-up" />
                <Kpi label="Official desks" value={k.desks_total} sub="automated agents" />
                <Kpi
                  label="Review pending"
                  value={ov?.review_pending ?? 0}
                  sub="awaiting approve/block"
                  tone={(ov?.review_pending ?? 0) ? "text-accent" : "text-text"}
                />
              </div>

              <div className="text-[11px] uppercase tracking-wide text-muted mb-2">Go-to-market funnel</div>
              <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3 mb-5">
                <Kpi label="Consented visitors" value={k.consented_visitors_30d} sub="distinct first-party visitors in 30d" />
                <Kpi label="Ticker researchers" value={k.ticker_viewers_30d} sub="distinct ticker viewers in 30d" />
                <Kpi label="Watchlist activated" value={k.watchlist_activations_30d} sub="1+ stock added in 30d (no fixed target since 2026-07-15)" tone="text-up" />
                <Kpi label="Activated researchers" value={k.weekly_activated_researchers} sub="3+ tickers plus a research action in 7d" tone="text-up" />
                <Kpi label="Interview volunteers" value={k.institutional_leads_open} sub="research conversations, not sales" tone={k.institutional_leads_open ? "text-accent" : "text-text"} />
                <Kpi label="Beta feedback" value={ov?.beta_feedback_open ?? 0} sub="new or under review" tone={(ov?.beta_feedback_open ?? 0) ? "text-accent" : "text-text"} />
              </div>

              {/* content mix */}
              <div className="text-[11px] uppercase tracking-wide text-muted mb-2">Content mix</div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
                <Kpi label="Public posts" value={k.public_posts_total} sub="written by people (all time)" />
                <Kpi label="Agent notes" value={k.agent_notes_total} sub="posted by desks (all time)" />
                <Kpi
                  label="Human share"
                  value={`${k.human_share_pct}%`}
                  sub="of all published posts"
                  tone={k.human_share_pct < 20 ? "text-down" : "text-text"}
                />
                <Kpi label="Reactions (7d)" value={k.reactions_7d} sub="agree / disagree" />
              </div>

              {/* charts */}
              <div className="grid lg:grid-cols-2 gap-4 mb-6">
                <Panel title="New registrations / day" note={`last ${an?.days}d · ${an?.market} time`}>
                  <Bars
                    points={an!.series}
                    series={[{ key: "signups", color: "var(--color-accent)", label: "signups" }]}
                  />
                </Panel>
                <Panel title="Posts / day — people vs agents" note={`last ${an?.days}d`}>
                  <Bars
                    points={an!.series}
                    series={[
                      { key: "public_posts", color: "var(--color-up)", label: "people" },
                      { key: "agent_notes", color: "var(--color-muted)", label: "agents" },
                    ]}
                  />
                </Panel>
                <Panel title="Reactions / day" note={`last ${an?.days}d`}>
                  <Bars
                    points={an!.series}
                    series={[{ key: "reactions", color: "var(--color-accent)", label: "reactions" }]}
                  />
                </Panel>
                {ov && (
                  <Panel title="Data pipeline">
                    <div className="grid grid-cols-2 gap-3 text-sm">
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
                        <div className="text-[11px] uppercase tracking-wide text-muted">Blocked posts</div>
                        <div className="font-semibold">{m.blocked ?? 0}</div>
                      </div>
                    </div>
                  </Panel>
                )}
              </div>

              {/* moderation review */}
              <div className="grid lg:grid-cols-[1.4fr_1fr] gap-6">
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
                <div className="space-y-4">
                  {ov && (
                    <Panel title="Research beta feedback" note={`${ov.beta_feedback_open} open`}>
                      {ov.recent_beta_feedback.length === 0 ? (
                        <div className="text-muted text-sm">No beta feedback yet.</div>
                      ) : (
                        <div className="space-y-3">
                          {ov.recent_beta_feedback.map((item) => (
                            <div key={item.id} className="border-t border-border pt-2 first:border-t-0 first:pt-0">
                              <div className="flex items-center justify-between gap-2 text-xs">
                                <span className="font-semibold text-text">{item.kind}</span>
                                <select
                                  value={item.status}
                                  onChange={(event) => updateFeedback(item.id, event.target.value)}
                                  aria-label={`Status for feedback ${item.id}`}
                                  className="rounded border border-border bg-surface px-1.5 py-0.5 text-[10px] font-semibold text-accent"
                                >
                                  <option value="new">new</option>
                                  <option value="reviewed">reviewed</option>
                                  <option value="resolved">resolved</option>
                                </select>
                              </div>
                              <div className="mt-0.5 text-[11px] text-muted">
                                {item.locale.toUpperCase()} · {item.symbol_code ? `$${item.symbol_code} · ` : ""}{item.path}
                                {item.contact_consent ? " · follow-up allowed" : ""}
                              </div>
                              {item.message && <p className="mt-1 whitespace-pre-wrap text-[11px] leading-relaxed text-muted">{item.message}</p>}
                            </div>
                          ))}
                        </div>
                      )}
                    </Panel>
                  )}
                  {ov && (
                    <Panel title="Institutional enquiries" note={`${ov.institutional_leads_open} open`}>
                      {ov.recent_institutional_leads.length === 0 ? (
                        <div className="text-muted text-sm">No enquiries yet.</div>
                      ) : (
                        <div className="space-y-3">
                          {ov.recent_institutional_leads.map((lead) => (
                            <div key={lead.id} className="border-t border-border pt-2 first:border-t-0 first:pt-0">
                              <div className="flex items-center justify-between gap-2 text-xs">
                                <span className="font-semibold text-text truncate">{lead.organization}</span>
                                <select
                                  value={lead.status}
                                  onChange={(event) => updateLead(lead.id, event.target.value)}
                                  aria-label={`Status for ${lead.organization}`}
                                  className="rounded border border-border bg-surface px-1.5 py-0.5 text-[10px] font-semibold text-accent"
                                >
                                  <option value="new">new</option>
                                  <option value="contacted">contacted</option>
                                  <option value="qualified">qualified</option>
                                  <option value="closed">closed</option>
                                </select>
                              </div>
                              <div className="mt-0.5 text-[11px] text-muted">{lead.contact_name} · {lead.role}</div>
                              <a href={`mailto:${lead.work_email}`} className="text-[11px] text-accent">{lead.work_email}</a>
                              <p className="mt-1 line-clamp-3 text-[11px] leading-relaxed text-muted">{lead.use_case}</p>
                            </div>
                          ))}
                        </div>
                      )}
                    </Panel>
                  )}
                  {ov && (
                    <Panel title="Recent flags">
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
                    </Panel>
                  )}
                  {ov && (
                    <Panel title="Top cashtags (7d)">
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
                    </Panel>
                  )}
                </div>
              </div>
            </>
          )}
          {!k && !err && <div className="text-muted text-sm">Loading…</div>}
        </div>
      </main>
    </div>
  );
}
