import { useEffect, useRef, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { api, type MarketStatus } from "../lib/api";
import { useAuth } from "../lib/auth";
import { usePageViewTracking } from "../lib/analytics";
import { type Lang, SUPPORTED, useLang } from "../lib/i18n";
import { Link, NavLink, useSwitchLang } from "../lib/nav";
import { useTenantConfig } from "../lib/tenant";
import { SearchBar } from "./SearchBar";

// Live, holiday-aware market status + the delay note — a pulsing green dot while open.
function MarketStatusPill() {
  const { t } = useLang();
  const { config } = useTenantConfig();
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
  const delayed = config.features.intraday_quotes && (open || preopen);
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

const ALL_TABS = [
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

const LANGUAGE_OPTIONS: Record<Lang, { compact: string; name: string }> = {
  bn: { compact: "🇧🇩 বাং", name: "বাংলা" },
  en: { compact: "🇬🇧 EN", name: "English" },
};

function LanguageSelect() {
  const { lang, t } = useLang();
  const { config } = useTenantConfig();
  const switchLang = useSwitchLang();
  const locales = config.supported_locales.filter((locale): locale is Lang =>
    SUPPORTED.includes(locale as Lang),
  );
  return (
    <select
      aria-label={t("header.language")}
      title={t("header.language")}
      value={locales.includes(lang) ? lang : config.default_locale}
      onChange={(event) => switchLang(event.target.value as Lang)}
      className="h-7 max-w-[76px] rounded-full border border-border bg-card px-1.5 text-[10px] font-semibold text-text outline-none focus:border-accent"
    >
      {locales.map((locale) => (
        <option key={locale} value={locale} title={LANGUAGE_OPTIONS[locale].name}>
          {LANGUAGE_OPTIONS[locale].compact}
        </option>
      ))}
    </select>
  );
}

export function Shell() {
  const { lang, t } = useLang();
  const { config } = useTenantConfig();
  const location = useLocation();
  const betaSource = location.pathname.endsWith("/beta")
    ? new URLSearchParams(location.search).get("from") || "/"
    : location.pathname + location.search;
  usePageViewTracking(true);
  const tagline = lang === "bn" ? config.tagline_bn : config.tagline_en;
  const tabs = ALL_TABS.filter((tab) => {
    if (tab.to === "/ideas") return config.features.strategy_scanner;
    if (tab.to === "/markets") return config.features.curated_screens;
    return true;
  });
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
          <Link to="/" aria-label={`${config.brand_name} — home`} className="flex min-w-0 flex-1 items-center gap-2">
            <img src={config.logo_url} alt={config.brand_name} className="h-8 w-8 shrink-0" />
            <div className="leading-tight min-w-0">
              <div className="truncate text-sm font-bold">{config.brand_name}</div>
              <div lang={lang} className="truncate text-[10px] font-semibold text-accent">
                {tagline}
              </div>
            </div>
          </Link>
          {/* Header noise cut 2026-07: Facebook + About moved to the Me page. What remains is
              what the user needs every session — status, alerts, language. */}
          <div className="ml-auto flex items-center gap-1.5 shrink-0">
            <MarketStatusPill />
            <AlertsBell />
            <LanguageSelect />
          </div>
        </div>
        <SearchBar />
      </header>

      {config.research_beta && (
        <div className="flex items-center justify-between gap-3 border-b border-accent/30 bg-accent/8 px-4 py-2 text-[10px] leading-tight">
          <span className="font-semibold text-accent">{lang === "bn" ? "রিসার্চ বেটা · তথ্য অসম্পূর্ণ হতে পারে" : "Research beta · data may be incomplete"}</span>
          <Link to={`/beta?from=${encodeURIComponent(betaSource)}`} className="shrink-0 font-semibold text-text underline decoration-border underline-offset-2">
            {lang === "bn" ? "মতামত দিন" : "Give feedback"}
          </Link>
        </div>
      )}

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
