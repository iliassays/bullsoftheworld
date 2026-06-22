import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { Pct, Spinner, taka } from "../components/ui";
export function Markets() {
    const [quotes, setQuotes] = useState(null);
    const [q, setQ] = useState("");
    useEffect(() => {
        api.quotes().then(setQuotes).catch(() => setQuotes([]));
    }, []);
    const filtered = useMemo(() => (quotes ?? []).filter((x) => x.code.includes(q.toUpperCase())), [quotes, q]);
    if (quotes === null)
        return _jsx(Spinner, {});
    return (_jsxs("div", { className: "flex flex-col gap-2", children: [_jsx("input", { value: q, onChange: (e) => setQ(e.target.value), placeholder: "Search code, e.g. GP", className: "bg-surface border border-border rounded-xl px-3 py-2 text-sm outline-none focus:border-accent" }), _jsx("div", { className: "text-[11px] uppercase tracking-wide text-muted px-1 mt-1", children: "Top movers" }), filtered.map((x) => (_jsxs(Link, { to: `/s/${x.code}`, className: "flex items-center bg-surface border border-border rounded-xl px-3 py-2.5", children: [_jsxs("div", { className: "font-bold text-sm", children: ["$", x.code] }), _jsxs("div", { className: "ml-auto text-right", children: [_jsx("div", { className: "text-sm tnum", children: taka(x.ltp) }), _jsx("div", { className: "text-xs font-semibold", children: _jsx(Pct, { value: x.change_pct }) })] })] }, x.code)))] }));
}
