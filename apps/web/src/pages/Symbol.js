import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Composer } from "../components/Composer";
import { PostCard } from "../components/PostCard";
import { Empty, Pct, Spinner, taka } from "../components/ui";
export function SymbolPage() {
    const { code = "" } = useParams();
    const sym = code.toUpperCase();
    const { user } = useAuth();
    const [detail, setDetail] = useState(null);
    const [posts, setPosts] = useState(null);
    const [watched, setWatched] = useState(false);
    useEffect(() => {
        setDetail(null);
        setPosts(null);
        api.symbol(sym).then(setDetail).catch(() => setDetail(null));
        api.feed(sym).then(setPosts).catch(() => setPosts([]));
        if (user)
            api.watchlist().then((w) => setWatched(w.some((i) => i.symbol.code === sym)));
    }, [sym, user]);
    const toggleWatch = async () => {
        if (watched)
            await api.watchRemove(sym);
        else
            await api.watchAdd(sym);
        setWatched(!watched);
    };
    if (detail === null)
        return _jsx(Spinner, {});
    const q = detail.quote;
    return (_jsxs("div", { className: "flex flex-col gap-3", children: [_jsxs("div", { className: "bg-surface border border-border rounded-2xl p-4", children: [_jsxs("div", { className: "flex items-start", children: [_jsxs("div", { children: [_jsxs("div", { className: "text-xl font-bold text-accent", children: ["$", sym] }), _jsx("div", { className: "text-xs text-muted", children: detail.symbol.name_en })] }), user && (_jsx("button", { onClick: toggleWatch, className: `ml-auto text-sm px-3 py-1.5 rounded-full border ${watched ? "text-accent border-accent bg-accent/10" : "text-muted border-border"}`, children: watched ? "★ Watching" : "☆ Watch" }))] }), q ? (_jsxs("div", { className: "mt-3 flex items-end gap-3", children: [_jsx("div", { className: "text-2xl font-bold tnum", children: taka(q.ltp) }), _jsx("div", { className: "text-sm font-semibold pb-1", children: _jsx(Pct, { value: q.change_pct }) }), _jsxs("div", { className: "ml-auto text-right text-xs text-muted tnum", children: [_jsxs("div", { children: ["H ", q.high, " \u00B7 L ", q.low] }), _jsxs("div", { children: ["Vol ", q.volume.toLocaleString()] })] })] })) : (_jsx("div", { className: "text-muted text-sm mt-2", children: "No quote yet." })), _jsxs("div", { className: "text-[10px] text-muted mt-2", children: ["\u23F1 delayed \u00B7 as of ", new Date(q?.as_of ?? "").toLocaleString()] })] }), user && _jsx(Composer, { initial: `$${sym} `, onPosted: (p) => setPosts((c) => [p, ...(c ?? [])]) }), posts === null ? (_jsx(Spinner, {})) : posts.length === 0 ? (_jsxs(Empty, { children: ["No posts about $", sym, " yet."] })) : (posts.map((p) => _jsx(PostCard, { post: p }, p.id)))] }));
}
