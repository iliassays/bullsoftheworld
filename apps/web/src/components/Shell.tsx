import { useEffect, useRef, useState } from "react";
import { Outlet } from "react-router-dom";
import { api, type MarketStatus } from "../lib/api";
import { useAuth } from "../lib/auth";
import { usePageViewTracking } from "../lib/analytics";
import { type Lang, useLang } from "../lib/i18n";
import { Link, NavLink, useSwitchLang } from "../lib/nav";
import { useTenantConfig } from "../lib/tenant";
import { SearchBar } from "./SearchBar";

// Live, holiday-aware market status + the delay note — a pulsing green dot while open.
function MarketStatusPill() {
  const { t } = useLang();
  const [st, setSt] = useState<MarketStatus | null>(null);
  useEffect(() => {
    let live = true;
    const load = () =>
      api
        .marketStatus()
        .then((s) => live && setSt(s))
        .catch(() => {});
    load();
    const id = setInterval(load, 60000); // flip open↔closed across the session boundary
    return () => {
      live = false;
      clearInterval(id);
    };
  }, []);
  const phase = st?.phase;
  const open = phase === "open";
  const preopen = phase === "pre_open";
  const dot = open ? "bg-up" : preopen ? "bg-accent" : "bg-muted";
  const label = open ? t("mkt.open") : preopen ? t("mkt.preOpen") : t("mkt.closed");
  const delayed = open || preopen;
  return (
    <span className="flex items-center gap-1.5 text-muted border border-border px-2 py-1 rounded-2xl shrink-0">
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${dot} ${open ? "animate-pulse" : ""}`} />
      <span className="flex flex-col leading-none gap-0.5">
        <span className="text-[10px] font-semibold text-text">{label}</span>
        {delayed && <span className="text-[9px] whitespace-nowrap">{t("delayed")}</span>}
      </span>
    </span>
  );
}

const tabs = [
  { to: "/", icon: "🏠", key: "nav.home", end: true },
  { to: "/ideas", icon: "💡", key: "nav.ideas" },
  { to: "/markets", icon: "📊", key: "nav.markets" },
  { to: "/portfolio", icon: "💼", key: "nav.portfolio" },
  { to: "/me", icon: "👤", key: "nav.me" },
];

// Header alerts bell: unread count for the signed-in user, refreshed on a slow poll.
// Hidden entirely when logged out — alerts are per-user by definition.
function AlertsBell() {
  const { user } = useAuth();
  const { t } = useLang();
  const [unread, setUnread] = useState(0);
  useEffect(() => {
    if (!user) return;
    let live = true;
    const load = () =>
      api
        .alertsUnread()
        .then((r) => live && setUnread(r.unread))
        .catch(() => {});
    load();
    const id = setInterval(load, 60000);
    return () => {
      live = false;
      clearInterval(id);
    };
  }, [user]);
  if (!user) return null;
  return (
    <Link
      to="/alerts"
      aria-label={t("nav.alerts")}
      title={t("nav.alerts")}
      className="relative text-muted hover:text-accent transition p-1 text-lg leading-none"
    >
      🔔
      {unread > 0 && (
        <span className="absolute -top-0.5 -right-0.5 min-w-[15px] h-[15px] rounded-full bg-down text-white text-[9px] font-bold grid place-items-center px-0.5">
          {unread > 99 ? "99+" : unread}
        </span>
      )}
    </Link>
  );
}

function LangToggle() {
  const { lang } = useLang();
  const switchLang = useSwitchLang();
  const opts: { id: Lang; label: string }[] = [
    { id: "bn", label: "🇧🇩 বাং" },
    { id: "en", label: "🇬🇧 EN" },
  ];
  return (
    <div className="flex rounded-full border border-border overflow-hidden text-[10px] font-semibold">
      {opts.map((o) => (
        <button
          key={o.id}
          onClick={() => switchLang(o.id)}
          aria-pressed={lang === o.id}
          className={`px-2 py-1 ${lang === o.id ? "bg-accent text-black" : "text-muted"}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Shell() {
  const { lang, t } = useLang();
  const { config } = useTenantConfig();
  usePageViewTracking(); // GA4 SPA page_view on route change + view_stock on stock pages
  const tagline =
    config.market === "US"
      ? lang === "bn"
        ? "যুক্তরাষ্ট্রের বাজার তথ্য, গুজব নয়"
        : "US market intelligence, not noise"
      : t("tagline");
  // Publish the live header height as a CSS var so page-level tab bars can stick right below
  // it (`top: var(--app-header-h)`). Measured, not hardcoded — the header wraps differently
  // per language and viewport.
  const headerRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const el = headerRef.current;
    if (!el) return;
    const apply = () =>
      document.documentElement.style.setProperty("--app-header-h", `${el.offsetHeight}px`);
    apply();
    const ro = new ResizeObserver(apply);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return (
    <div className="min-h-full max-w-[480px] mx-auto flex flex-col bg-bg">
      <header
        ref={headerRef}
        className="sticky top-0 z-20 bg-nav/90 backdrop-blur border-b border-border px-4 py-3 flex flex-col gap-2.5"
      >
        <div className="flex items-center gap-2.5">
          <Link to="/" aria-label={`${config.brand_name} — home`} className="flex items-center gap-2.5 min-w-0">
            <img src="/logo-mark-v2.png" alt={config.brand_name} className="w-9 h-9 shrink-0" />
            <div className="leading-tight min-w-0">
              <div className="font-bold text-base whitespace-nowrap">{config.brand_name}</div>
              <div lang={lang} className="text-[11px] text-accent font-semibold truncate">
                {tagline}
              </div>
            </div>
          </Link>
          {/* Header noise cut 2026-07: Facebook + About moved to the Me page. What remains is
              what the user needs every session — status, alerts, language. */}
          <div className="ml-auto flex items-center gap-1.5 shrink-0">
            <MarketStatusPill />
            <AlertsBell />
            <LangToggle />
          </div>
        </div>
        <SearchBar />
      </header>

      {/* Remount on language switch so all pages refetch dynamic content in the new locale.
          pb-24 clears the fixed bottom nav so the last content isn't hidden behind it. */}
      <main key={lang} className="flex-1 px-3 py-3 pb-24">
        <Outlet />
      </main>

      {/* Fixed (not sticky): a sticky last-child has no scroll room below it, so it wouldn't pin to
          the viewport. Centered within the 480px column; extra bottom inset for the phone home bar. */}
      <nav
        className="fixed bottom-0 left-0 right-0 z-20 mx-auto max-w-[480px] bg-nav/92 backdrop-blur border-t border-border flex justify-around items-center px-2 py-2"
        style={{ paddingBottom: "calc(0.875rem + env(safe-area-inset-bottom))" }}
      >
        {tabs.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.end}
            className={({ isActive }) =>
              `flex flex-col items-center gap-0.5 text-[10px] ${isActive ? "text-accent" : "text-muted"}`
            }
          >
            <span className="text-lg">{tab.icon}</span>
            {t(tab.key)}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
