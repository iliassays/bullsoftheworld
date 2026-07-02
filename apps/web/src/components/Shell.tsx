import { useEffect, useState } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { api, type MarketStatus } from "../lib/api";
import { type Lang, useLang } from "../lib/i18n";
import { SearchBar } from "./SearchBar";

// Bulls of Dhaka's Facebook page (numeric id works even without a vanity URL).
const FB_URL = "https://www.facebook.com/1214682241723822";

function FbIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden>
      <path d="M22 12a10 10 0 1 0-11.6 9.9v-7H7.9V12h2.5V9.8c0-2.5 1.5-3.9 3.8-3.9 1.1 0 2.2.2 2.2.2v2.4h-1.3c-1.2 0-1.6.77-1.6 1.55V12h2.8l-.45 2.9h-2.35v7A10 10 0 0 0 22 12z" />
    </svg>
  );
}

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
  { to: "/", icon: "🏠", key: "nav.feed", end: true },
  { to: "/markets", icon: "📊", key: "nav.markets" },
  { to: "/bulls", icon: "🐂", key: "nav.bulls" },
  { to: "/scanner", icon: "🛰️", key: "nav.scanner" },
  { to: "/me", icon: "👤", key: "nav.me" },
];

function LangToggle() {
  const { lang, setLang } = useLang();
  const opts: { id: Lang; label: string }[] = [
    { id: "bn", label: "🇧🇩 বাং" },
    { id: "en", label: "🇬🇧 EN" },
  ];
  return (
    <div className="flex rounded-full border border-border overflow-hidden text-[10px] font-semibold">
      {opts.map((o) => (
        <button
          key={o.id}
          onClick={() => setLang(o.id)}
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
  return (
    <div className="min-h-full max-w-[480px] mx-auto flex flex-col bg-bg">
      <header className="sticky top-0 z-20 bg-bg/85 backdrop-blur border-b border-border px-4 py-3 flex flex-col gap-2.5">
        <div className="flex items-center gap-2.5">
          <Link to="/" aria-label="Bulls of Dhaka — home" className="flex items-center gap-2.5 min-w-0">
            <img src="/logo-mark-v2.png" alt="Bulls of Dhaka" className="w-9 h-9 shrink-0" />
            <div className="leading-tight min-w-0">
              <div className="font-bold text-base whitespace-nowrap">Bulls of Dhaka</div>
              <div lang={lang} className="text-[11px] text-accent font-semibold truncate">
                {t("tagline")}
              </div>
            </div>
          </Link>
          <div className="ml-auto flex items-center gap-1.5 shrink-0">
            <MarketStatusPill />
            <a
              href={FB_URL}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Bulls of Dhaka on Facebook"
              className="text-muted hover:text-accent transition p-1"
            >
              <FbIcon />
            </a>
            <Link
              to="/about"
              aria-label={t("nav.about")}
              title={t("nav.about")}
              className="text-muted hover:text-accent transition text-lg leading-none px-0.5"
            >
              ⓘ
            </Link>
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
        className="fixed bottom-0 left-0 right-0 z-20 mx-auto max-w-[480px] bg-bg/92 backdrop-blur border-t border-border flex justify-around items-center px-2 py-2"
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
