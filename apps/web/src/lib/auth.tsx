import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, tokenStore, type User } from "./api";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (identifier: string, password: string) => Promise<void>;
  register: (name: string, contact: string, password: string) => Promise<void>;
  applyToken: (token: string) => Promise<void>;
  logout: () => void;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!tokenStore.get()) return setLoading(false);
    api
      .me()
      .then(setUser)
      .catch(() => tokenStore.clear())
      .finally(() => setLoading(false));
  }, []);

  const finishAuth = async (token: string) => {
    tokenStore.set(token);
    setUser(await api.me());
  };

  return (
    <Ctx.Provider
      value={{
        user,
        loading,
        login: async (identifier, password) =>
          finishAuth((await api.login({ identifier, password })).access_token),
        register: async (name, contact, password) =>
          finishAuth((await api.register({ name, contact, password })).access_token),
        applyToken: finishAuth,
        logout: () => {
          tokenStore.clear();
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
