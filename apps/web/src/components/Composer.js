import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from "react";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
export function Composer({ onPosted, initial = "", }) {
    const { user } = useAuth();
    const [body, setBody] = useState(initial);
    const [sentiment, setSentiment] = useState(null);
    const [busy, setBusy] = useState(false);
    const [err, setErr] = useState("");
    if (!user)
        return null;
    const submit = async () => {
        if (!body.trim())
            return;
        setBusy(true);
        setErr("");
        try {
            const post = await api.createPost({ body: body.trim(), sentiment });
            onPosted(post);
            setBody("");
            setSentiment(null);
        }
        catch (e) {
            setErr(e instanceof ApiError ? e.detail : "Failed to post");
        }
        finally {
            setBusy(false);
        }
    };
    const tone = (s) => `text-xs font-bold px-3 py-1.5 rounded-full border transition ${sentiment === s
        ? s === "bull"
            ? "text-up border-up bg-up/10"
            : "text-down border-down bg-down/10"
        : "text-muted border-border"}`;
    return (_jsxs("div", { className: "bg-surface border border-border rounded-2xl p-4", children: [_jsx("textarea", { value: body, onChange: (e) => setBody(e.target.value), placeholder: "What's your call? Use $GP to tag a stock\u2026", rows: 3, className: "w-full bg-transparent resize-none outline-none text-[15px] placeholder:text-muted" }), _jsxs("div", { className: "flex items-center gap-2 mt-2", children: [_jsx("button", { type: "button", className: tone("bull"), onClick: () => setSentiment(sentiment === "bull" ? null : "bull"), children: "\u25B2 Bull" }), _jsx("button", { type: "button", className: tone("bear"), onClick: () => setSentiment(sentiment === "bear" ? null : "bear"), children: "\u25BC Bear" }), _jsx("button", { type: "button", disabled: busy || !body.trim(), onClick: submit, className: "ml-auto bg-accent text-bg font-bold text-sm px-4 py-1.5 rounded-full disabled:opacity-40", children: busy ? "…" : "Post" })] }), err && _jsx("p", { className: "text-down text-xs mt-2", children: err })] }));
}
