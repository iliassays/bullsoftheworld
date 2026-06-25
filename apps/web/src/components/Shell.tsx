import { NavLink, Outlet } from "react-router-dom";
import { SearchBar } from "./SearchBar";

const tabs = [
  { to: "/", icon: "🏠", label: "Feed", end: true },
  { to: "/markets", icon: "📊", label: "Markets" },
  { to: "/bulls", icon: "🐂", label: "Bulls" },
  { to: "/watchlist", icon: "⭐", label: "Watch" },
  { to: "/me", icon: "👤", label: "Me" },
];

export function Shell() {
  return (
    <div className="min-h-full max-w-[480px] mx-auto flex flex-col bg-bg">
      <header className="sticky top-0 z-20 bg-bg/85 backdrop-blur border-b border-border px-4 py-3 flex flex-col gap-2.5">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg grid place-items-center text-lg bg-gradient-to-br from-accent to-[#c8901a] shadow-[0_4px_14px_rgba(245,184,46,0.35)]">
            🐂
          </div>
          <div className="leading-tight">
            <div className="font-bold text-base">Bulls of Dhaka</div>
            <div lang="bn" className="text-[11px] text-accent font-semibold">
              ঢাকার ষাঁড়
            </div>
          </div>
          <div className="ml-auto text-[10px] text-muted border border-border px-2 py-1 rounded-full">
            ⏱ Delayed
          </div>
        </div>
        <SearchBar />
      </header>

      <main className="flex-1 px-3 py-3">
        <Outlet />
      </main>

      <nav className="sticky bottom-0 bg-bg/92 backdrop-blur border-t border-border flex justify-around items-center px-2 py-2 pb-3.5">
        {tabs.map((t) => (
          <NavLink
            key={t.to}
            to={t.to}
            end={t.end}
            className={({ isActive }) =>
              `flex flex-col items-center gap-0.5 text-[10px] ${isActive ? "text-accent" : "text-muted"}`
            }
          >
            <span className="text-lg">{t.icon}</span>
            {t.label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
