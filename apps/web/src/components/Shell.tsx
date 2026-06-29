import { Link, NavLink, Outlet } from "react-router-dom";
import { type Lang, useLang } from "../lib/i18n";
import { SearchBar } from "./SearchBar";

const tabs = [
  { to: "/", icon: "🏠", key: "nav.feed", end: true },
  { to: "/markets", icon: "📊", key: "nav.markets" },
  { to: "/bulls", icon: "🐂", key: "nav.bulls" },
  { to: "/watchlist", icon: "⭐", key: "nav.watch" },
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
              <div className="font-bold text-base">Bulls of Dhaka</div>
              <div lang={lang} className="text-[11px] text-accent font-semibold truncate">
                {t("tagline")}
              </div>
            </div>
          </Link>
          <div className="ml-auto flex items-center gap-2 shrink-0">
            <LangToggle />
            <span className="text-[10px] text-muted border border-border px-2 py-1 rounded-full">
              ⏱ {t("delayed")}
            </span>
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
