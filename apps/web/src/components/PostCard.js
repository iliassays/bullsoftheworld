import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Link } from "react-router-dom";
import { Avatar, SentimentTag } from "./ui";
const ago = (iso) => {
    const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
    if (s < 60)
        return `${s}s`;
    if (s < 3600)
        return `${Math.floor(s / 60)}m`;
    if (s < 86400)
        return `${Math.floor(s / 3600)}h`;
    return `${Math.floor(s / 86400)}d`;
};
// Render body with $CASHTAGS linked to their symbol page.
function Body({ text }) {
    const parts = text.split(/(\$[A-Za-z0-9]{2,16})/g);
    return (_jsx("p", { className: "text-[15px] leading-relaxed text-text/90 my-2 break-words", children: parts.map((p, i) => /^\$[A-Za-z0-9]{2,16}$/.test(p) ? (_jsx(Link, { to: `/s/${p.slice(1).toUpperCase()}`, className: "text-accent font-semibold", children: p.toUpperCase() }, i)) : (_jsx("span", { children: p }, i))) }));
}
export function PostCard({ post }) {
    return (_jsxs("article", { className: "bg-surface border border-border rounded-2xl p-4", children: [_jsxs("header", { className: "flex items-center gap-2.5", children: [_jsx(Avatar, { name: post.author.name }), _jsxs("div", { className: "leading-tight", children: [_jsx("b", { className: "text-sm", children: post.author.name }), _jsxs("span", { className: "block text-xs text-muted", children: ["@", post.author.handle, " \u00B7 ", ago(post.created_at)] })] }), _jsx("div", { className: "ml-auto", children: _jsx(SentimentTag, { s: post.sentiment }) })] }), _jsx(Body, { text: post.body }), post.cashtags.length > 0 && (_jsx("div", { className: "flex gap-1.5 flex-wrap", children: post.cashtags.map((c) => (_jsxs(Link, { to: `/s/${c}`, className: "text-xs text-accent bg-accent/10 px-2 py-0.5 rounded-full", children: ["$", c] }, c))) }))] }));
}
