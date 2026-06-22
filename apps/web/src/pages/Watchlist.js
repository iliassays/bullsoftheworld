import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Empty, Pct, Spinner, taka } from "../components/ui";
export function Watchlist() {
    const { user } = useAuth();
    const [items, setItems] = useState(null);
    useEffect(() => {
        if (user)
            api.watchlist().then(setItems).catch(() => setItems([]));
    }, [user]);
    if (!user)
        return (_jsxs(Empty, { children: [_jsx(Link, { to: "/me", className: "text-accent", children: "Log in" }), " ", "to build your watchlist."] }));
    if (items === null)
        return _jsx(Spinner, {});
    if (items.length === 0)
        return _jsx(Empty, { children: "Your watchlist is empty. Tap \u2606 on any symbol." });
    return (_jsx("div", { className: "flex flex-col gap-2", children: items.map(({ symbol, quote }) => (_jsxs(Link, { to: `/s/${symbol.code}`, className: "flex items-center bg-surface border border-border rounded-xl px-3 py-2.5", children: [_jsxs("div", { children: [_jsxs("div", { className: "font-bold text-sm", children: ["$", symbol.code] }), _jsx("div", { className: "text-xs text-muted", children: symbol.name_en })] }), quote && (_jsxs("div", { className: "ml-auto text-right", children: [_jsx("div", { className: "text-sm tnum", children: taka(quote.ltp) }), _jsx("div", { className: "text-xs font-semibold", children: _jsx(Pct, { value: quote.change_pct }) })] }))] }, symbol.code))) }));
}
