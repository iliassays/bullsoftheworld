import { jsx as _jsx } from "react/jsx-runtime";
import { createContext, useContext, useEffect, useState } from "react";
import { api, tokenStore } from "./api";
const Ctx = createContext(null);
export function AuthProvider({ children }) {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);
    useEffect(() => {
        if (!tokenStore.get())
            return setLoading(false);
        api
            .me()
            .then(setUser)
            .catch(() => tokenStore.clear())
            .finally(() => setLoading(false));
    }, []);
    const finishAuth = async (token) => {
        tokenStore.set(token);
        setUser(await api.me());
    };
    return (_jsx(Ctx.Provider, { value: {
            user,
            loading,
            login: async (handle, password) => finishAuth((await api.login({ handle, password })).access_token),
            register: async (handle, name, password) => finishAuth((await api.register({ handle, name, password })).access_token),
            logout: () => {
                tokenStore.clear();
                setUser(null);
            },
        }, children: children }));
}
export function useAuth() {
    const ctx = useContext(Ctx);
    if (!ctx)
        throw new Error("useAuth must be used within AuthProvider");
    return ctx;
}
