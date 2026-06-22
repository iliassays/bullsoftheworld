import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { NavLink, Outlet } from "react-router-dom";
const tabs = [
    { to: "/", icon: "🏠", label: "Feed", end: true },
    { to: "/markets", icon: "📊", label: "Markets" },
    { to: "/watchlist", icon: "⭐", label: "Watch" },
    { to: "/me", icon: "👤", label: "Me" },
];
export function Shell() {
    return (_jsxs("div", { className: "min-h-full max-w-[480px] mx-auto flex flex-col bg-bg", children: [_jsxs("header", { className: "sticky top-0 z-10 bg-bg/85 backdrop-blur border-b border-border px-4 py-3 flex items-center gap-2.5", children: [_jsx("div", { className: "w-8 h-8 rounded-lg grid place-items-center text-lg bg-gradient-to-br from-accent to-[#c8901a] shadow-[0_4px_14px_rgba(245,184,46,0.35)]", children: "\uD83D\uDC02" }), _jsxs("div", { className: "leading-tight", children: [_jsx("div", { className: "font-bold text-base", children: "Bulls of Dhaka" }), _jsx("div", { lang: "bn", className: "text-[11px] text-accent font-semibold", children: "\u09A2\u09BE\u0995\u09BE\u09B0 \u09B7\u09BE\u0981\u09A1\u09BC" })] }), _jsx("div", { className: "ml-auto text-[10px] text-muted border border-border px-2 py-1 rounded-full", children: "\u23F1 15-min delayed" })] }), _jsx("main", { className: "flex-1 px-3 py-3", children: _jsx(Outlet, {}) }), _jsx("nav", { className: "sticky bottom-0 bg-bg/92 backdrop-blur border-t border-border flex justify-around items-center px-2 py-2 pb-3.5", children: tabs.map((t) => (_jsxs(NavLink, { to: t.to, end: t.end, className: ({ isActive }) => `flex flex-col items-center gap-0.5 text-[10px] ${isActive ? "text-accent" : "text-muted"}`, children: [_jsx("span", { className: "text-lg", children: t.icon }), t.label] }, t.to))) })] }));
}
