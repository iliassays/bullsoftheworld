import { useEffect, useState } from "react";
import { useSeo } from "../components/Seo";
import { Link } from "../lib/nav";
import { api, type Portfolio as PortfolioData } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useLang } from "../lib/i18n";
import { useTenantConfig } from "../lib/tenant";
import { CompanyLogo } from "../components/CompanyLogo";
import { PortfolioGrowthChart } from "../components/PortfolioGrowthChart";
import { PriceAlertSheet } from "../components/PriceAlertSheet";
import { Empty, Pct, Spinner, taka } from "../components/ui";

// "3d", "5h" — same short form as PostCard's feed timestamps.
const ago = (iso: string) => {
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
};

// Manual holdings only: quantity + average buy price, typed in by the user. We never connect to a
// broker account — this is a notebook valued with the tenant's available delayed market data.
export function Portfolio() {
  const { user } = useAuth();
  const { t } = useLang();
  const { config } = useTenantConfig();
  useSeo({ noindex: true }); // private/personal — keep out of the index
  const [pf, setPf] = useState<PortfolioData | null>(null);
  const [adding, setAdding] = useState(false);
  const [code, setCode] = useState("");
  const [qty, setQty] = useState("");
  const [cost, setCost] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [alertSheetFor, setAlertSheetFor] = useState<string | null>(null);
  // Closing the loop: right after a NEW holding is added (not an edit of an existing one),
  // Nudge users toward an alert only where the tenant has a validated alerting feed.
  const [justAdded, setJustAdded] = useState<string | null>(null);

  const load = () =>
    api
      .portfolio()
      .then(setPf)
      .catch(() => setPf({ holdings: [], total_value: null, total_cost: 0, day_pnl: null, day_pnl_pct: null, total_pnl: null, total_pnl_pct: null }));
  useEffect(() => {
    if (user) load();
  }, [user]);

  const save = async () => {
    setErr(null);
    const q = Number(qty);
    const c = Number(cost);
    if (!code.trim() || !Number.isFinite(q) || q <= 0 || !Number.isFinite(c) || c <= 0) {
      setErr(t("pf.invalid"));
      return;
    }
    try {
      const upserted = await api.holdingUpsert({
        code: code.trim().toUpperCase(),
        quantity: q,
        avg_cost: c,
      });
      setAdding(false);
      setCode("");
      setQty("");
      setCost("");
      if (upserted.status === "created" && config.features.price_alerts) {
        setJustAdded(upserted.code);
      }
      load();
    } catch {
      setErr(t("pf.unknownCode"));
    }
  };

  if (!user)
    return (
      <div className="bg-surface border border-border rounded-2xl p-5 text-center">
        <div className="text-3xl">💼</div>
        <div className="font-bold mt-2">{t("pf.loginTitle")}</div>
        <p className="text-sm text-muted mt-1.5">{t("pf.loginBody")}</p>
        <Link
          to="/me"
          className="inline-block mt-3 rounded-full px-5 py-2 text-sm font-bold bg-accent text-bg hover:opacity-90"
        >
          {t("home.signInCta")}
        </Link>
      </div>
    );

  if (pf === null) return <Spinner />;

  return (
    <div className="flex flex-col gap-3">
      <div className="px-1">
        <h1 className="font-bold text-lg">💼 {t("pf.title")}</h1>
        <p className="text-xs text-muted">{t("pf.subtitle")}</p>
      </div>

      {/* Summary — the number the user opens the app for. */}
      <div className="bg-surface border border-border rounded-2xl p-4 text-center">
        <div className="text-[11px] text-muted uppercase tracking-wide">{t("pf.totalValue")}</div>
        <div className="text-3xl font-bold tnum mt-1">
          {pf.total_value != null ? taka(pf.total_value) : "—"}
        </div>
        {pf.day_pnl != null && (
          <div className="text-sm font-semibold mt-1">
            <span className={pf.day_pnl >= 0 ? "text-up" : "text-down"}>
              {pf.day_pnl >= 0 ? "+" : ""}
              {taka(pf.day_pnl)} {t("pf.today")}
            </span>
            {pf.total_pnl_pct != null && (
              <span className="text-muted font-normal">
                {" "}
                · {t("pf.allTime")} <Pct value={pf.total_pnl_pct} />
              </span>
            )}
          </div>
        )}
      </div>

      {pf.holdings.length > 0 && <PortfolioGrowthChart />}

      {/* Holdings */}
      {pf.holdings.length === 0 ? (
        <Empty>{t("pf.empty")}</Empty>
      ) : (
        <div className="bg-surface border border-border rounded-2xl p-3">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted px-1 pb-1">
            {t("pf.holdings")} · {pf.holdings.length}
          </div>
          {pf.holdings.map((h) => (
            <div key={h.code} className="py-2.5 border-t border-border first:border-t-0">
              <Link to={`/s/${h.code}`} className="flex items-center gap-2.5">
                <CompanyLogo code={h.code} size={30} />
                <div className="min-w-0">
                  <div className="text-sm font-bold">${h.code}</div>
                  <div className="text-[11px] text-muted tnum">
                    {h.quantity.toLocaleString()} × {taka(h.avg_cost)}
                  </div>
                </div>
                <div className="ml-auto text-right tnum">
                  <div className="text-sm font-semibold">
                    {h.value != null ? taka(h.value) : "—"}
                  </div>
                  {h.pnl_pct != null && (
                    <div className="text-xs font-semibold">
                      <Pct value={h.pnl_pct} period="sinceBuy" />
                    </div>
                  )}
                </div>
              </Link>

              {/* What's happening — not just P&L. The same alert already sitting in the bell
                  inbox (holders are already fanned out to), resurfaced right where it's useful. */}
              {h.latest_alert_title && (
                <Link
                  to={`/s/${h.code}`}
                  className="block mt-1.5 ml-[38px] text-[11px] text-muted leading-snug hover:text-fg"
                >
                  📌 {h.latest_alert_title}
                  {h.latest_alert_at && <span className="tnum"> · {ago(h.latest_alert_at)}</span>}
                </Link>
              )}
              {config.features.price_alerts && <div className="mt-1.5 ml-[38px]">
                {h.has_price_alert ? (
                  <button
                    onClick={() => setAlertSheetFor(h.code)}
                    className="text-[11px] font-semibold text-accent"
                  >
                    🔔 {t("pf.alertSet")}
                  </button>
                ) : (
                  <button
                    onClick={() => setAlertSheetFor(h.code)}
                    className="text-[11px] font-semibold text-muted hover:text-accent"
                  >
                    {t("pf.setAlert")}
                  </button>
                )}
              </div>}
              {config.features.price_alerts && alertSheetFor === h.code && (
                <div className="mt-2">
                  <PriceAlertSheet
                    code={h.code}
                    onClose={() => setAlertSheetFor(null)}
                    onChange={load}
                  />
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {config.features.price_alerts && justAdded && (
        <div className="bg-surface border border-accent/40 rounded-2xl p-3.5 flex items-center gap-3">
          <span className="text-lg">🔔</span>
          <p className="text-xs text-muted flex-1">{t("pf.postAddPrompt")}</p>
          <button
            onClick={() => {
              setAlertSheetFor(justAdded);
              setJustAdded(null);
            }}
            className="rounded-full px-3 py-1.5 text-xs font-bold bg-accent text-bg shrink-0"
          >
            {t("pf.setAlert")}
          </button>
          <button
            onClick={() => setJustAdded(null)}
            className="text-xs text-muted shrink-0"
          >
            {t("pf.notNow")}
          </button>
        </div>
      )}

      {/* Add / edit — same endpoint upserts by code, so re-adding a code updates it. */}
      {adding ? (
        <div className="bg-surface border border-accent/40 rounded-2xl p-4 flex flex-col gap-2">
          <div className="font-semibold text-sm">{t("pf.addTitle")}</div>
          <input
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder={t(config.market === "US" ? "pf.codePh.us" : "pf.codePh")}
            className="bg-bg border border-border rounded-xl px-3 py-2 text-sm uppercase"
          />
          <div className="flex gap-2">
            <input
              value={qty}
              onChange={(e) => setQty(e.target.value)}
              placeholder={t("pf.qtyPh")}
              inputMode="numeric"
              className="bg-bg border border-border rounded-xl px-3 py-2 text-sm flex-1 tnum"
            />
            <input
              value={cost}
              onChange={(e) => setCost(e.target.value)}
              placeholder={`${t("pf.costPh")} ${config.currency_symbol}`}
              inputMode="decimal"
              className="bg-bg border border-border rounded-xl px-3 py-2 text-sm flex-1 tnum"
            />
          </div>
          {err && <div className="text-xs text-down">{err}</div>}
          <div className="flex gap-2">
            <button
              onClick={save}
              className="flex-1 rounded-xl py-2.5 text-sm font-bold bg-accent text-bg hover:opacity-90"
            >
              {t("pf.save")}
            </button>
            <button
              onClick={() => setAdding(false)}
              className="rounded-xl px-4 py-2.5 text-sm font-semibold border border-border text-muted"
            >
              {t("pf.cancel")}
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setAdding(true)}
          className="rounded-2xl border border-border py-3 text-sm font-semibold text-muted hover:border-accent hover:text-accent"
        >
          ＋ {t("pf.addTitle")}
        </button>
      )}

      <p className="text-[10px] text-muted text-center px-4">
        {t(config.features.intraday_quotes ? "pf.disclaimer" : "pf.disclaimerEod")}
      </p>
    </div>
  );
}
