import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, refreshStore, tokenStore, type User } from "./api";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (identifier: string, password: string) => Promise<void>;
  register: (name: string, contact: string, password: string) => Promise<void>;
  applyToken: (token: string, refreshToken?: string | null) => Promise<void>;
  refresh: () => Promise<void>;
  logout: () => void;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Access tokens live only in memory. Restore from the HttpOnly refresh cookie on each load;
    // local development can still supply the legacy body token while using plain HTTP.
    api
      .restoreSession(refreshStore.get())
      .then((tokens) => {
        tokenStore.set(tokens.access_token);
        if (tokens.refresh_token) refreshStore.set(tokens.refresh_token);
        else refreshStore.clear();
        return api.me();
      })
      .then(setUser)
      .catch(() => {
        tokenStore.clear();
        refreshStore.clear();
      })
      .finally(() => setLoading(false));
  }, []);

  const finishAuth = async (token: string, refreshToken?: string | null) => {
    tokenStore.set(token);
    if (refreshToken) refreshStore.set(refreshToken);
    else refreshStore.clear();
    setUser(await api.me());
  };

  return (
    <Ctx.Provider
      value={{
        user,
        loading,
        login: async (identifier, password) => {
          const t = await api.login({ identifier, password });
          await finishAuth(t.access_token, t.refresh_token);
        },
        register: async (name, contact, password) => {
          const t = await api.register({ name, contact, password });
          await finishAuth(t.access_token, t.refresh_token);
        },
        applyToken: finishAuth,
        refresh: async () => setUser(await api.me()),
        logout: () => {
          // Best-effort server-side revocation — the tokens are cleared locally regardless.
          const rt = refreshStore.get();
          api.logout(rt).catch(() => {});
          tokenStore.clear();
          refreshStore.clear();
          setUser(null);
        },
      }}
    >
      {children}
    </Ctx.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
