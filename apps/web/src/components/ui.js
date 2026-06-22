import { jsxs as _jsxs, jsx as _jsx } from "react/jsx-runtime";
export const taka = (n) => `৳${n.toLocaleString("en-US", { minimumFractionDigits: 1 })}`;
export function Pct({ value }) {
    const up = value >= 0;
    return (_jsxs("span", { className: `tnum ${up ? "text-up" : "text-down"}`, children: [up ? "▲" : "▼", " ", Math.abs(value).toFixed(2), "%"] }));
}
export function SentimentTag({ s }) {
    if (!s)
        return null;
    const bull = s === "bull";
    return (_jsx("span", { className: `text-xs font-bold px-2 py-1 rounded-full ${bull ? "text-up bg-up/10" : "text-down bg-down/10"}`, children: bull ? "▲ Bull" : "▼ Bear" }));
}
export function Avatar({ name }) {
    const initials = name
        .split(" ")
        .map((w) => w[0])
        .slice(0, 2)
        .join("")
        .toUpperCase();
    return (_jsx("div", { className: "w-9 h-9 rounded-full grid place-items-center font-bold text-sm text-accent bg-card shrink-0", children: initials }));
}
export function Spinner() {
    return _jsx("div", { className: "text-muted text-sm py-8 text-center", children: "Loading\u2026" });
}
export function Empty({ children }) {
    return _jsx("div", { className: "text-muted text-sm py-10 text-center px-6", children: children });
}
