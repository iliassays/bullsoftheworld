import { jsxs as _jsxs, jsx as _jsx } from "react/jsx-runtime";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { Pct, taka } from "./ui";
export function TickerStrip() {
    const [quotes, setQuotes] = useState([]);
    useEffect(() => {
        api.quotes().then((q) => setQuotes(q.slice(0, 12))).catch(() => { });
    }, []);
    if (!quotes.length)
        return null;
    return (_jsx("div", { className: "flex gap-2 overflow-x-auto pb-1 -mx-1 px-1 [scrollbar-width:none]", children: quotes.map((q) => (_jsxs(Link, { to: `/s/${q.code}`, className: "shrink-0 min-w-[104px] bg-card border border-border rounded-xl px-3 py-2", children: [_jsxs("div", { className: "font-bold text-[13px]", children: ["$", q.code] }), _jsx("div", { className: "text-xs text-muted tnum", children: taka(q.ltp) }), _jsx("div", { className: "text-xs font-semibold mt-0.5", children: _jsx(Pct, { value: q.change_pct }) })] }, q.code))) }));
}
