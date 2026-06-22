import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Composer } from "../components/Composer";
import { PostCard } from "../components/PostCard";
import { TickerStrip } from "../components/TickerStrip";
import { Empty, Spinner } from "../components/ui";
export function Feed() {
    const { user } = useAuth();
    const [posts, setPosts] = useState(null);
    useEffect(() => {
        api.feed().then(setPosts).catch(() => setPosts([]));
    }, []);
    return (_jsxs("div", { className: "flex flex-col gap-3", children: [_jsx(TickerStrip, {}), user ? (_jsx(Composer, { onPosted: (p) => setPosts((cur) => [p, ...(cur ?? [])]) })) : (_jsx(Link, { to: "/me", className: "block text-center text-sm text-accent bg-surface border border-border rounded-2xl py-3", children: "Log in to post your call \u2192" })), posts === null ? (_jsx(Spinner, {})) : posts.length === 0 ? (_jsx(Empty, { children: "No posts yet. Be the first to call $GP." })) : (posts.map((p) => _jsx(PostCard, { post: p }, p.id)))] }));
}
