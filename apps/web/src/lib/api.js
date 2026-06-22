// Minimal typed API client. Token is injected from localStorage.
const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
const TOKEN_KEY = "bulls.token";
export const tokenStore = {
    get: () => localStorage.getItem(TOKEN_KEY),
    set: (t) => localStorage.setItem(TOKEN_KEY, t),
    clear: () => localStorage.removeItem(TOKEN_KEY),
};
export class ApiError extends Error {
    constructor(status, detail) {
        super(detail);
        Object.defineProperty(this, "status", {
            enumerable: true,
            configurable: true,
            writable: true,
            value: status
        });
        Object.defineProperty(this, "detail", {
            enumerable: true,
            configurable: true,
            writable: true,
            value: detail
        });
    }
}
async function request(path, opts = {}) {
    const headers = {
        "Content-Type": "application/json",
        ...opts.headers,
    };
    const token = tokenStore.get();
    if (token)
        headers.Authorization = `Bearer ${token}`;
    const res = await fetch(`${BASE}${path}`, { ...opts, headers });
    if (res.status === 204)
        return undefined;
    const body = await res.json().catch(() => ({}));
    if (!res.ok)
        throw new ApiError(res.status, body?.detail ?? res.statusText);
    return body;
}
export const api = {
    // auth
    register: (b) => request("/auth/register", {
        method: "POST",
        body: JSON.stringify(b),
    }),
    login: (b) => request("/auth/login", {
        method: "POST",
        body: JSON.stringify(b),
    }),
    me: () => request("/auth/me"),
    // market
    quotes: (codes) => request(`/quotes${codes?.length ? `?codes=${codes.join(",")}` : ""}`),
    symbol: (code) => request(`/symbols/${code}`),
    // posts
    feed: (code) => request(`/posts${code ? `?code=${code}` : ""}`),
    createPost: (b) => request("/posts", { method: "POST", body: JSON.stringify(b) }),
    // watchlist
    watchlist: () => request("/watchlist"),
    watchAdd: (code) => request("/watchlist", {
        method: "POST",
        body: JSON.stringify({ code }),
    }),
    watchRemove: (code) => request(`/watchlist/${code}`, { method: "DELETE" }),
};
