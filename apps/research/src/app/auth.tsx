import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { researchApi, type ResearchUser } from "./api-client";
import { isResearchPreview } from "./deployment";

interface ResearchAuthState {
  user: ResearchUser | null;
  loading: boolean;
  error: string | null;
  login(identifier: string, password: string): Promise<void>;
  logout(): Promise<void>;
}

const Context = createContext<ResearchAuthState | null>(null);

const PREVIEW_USER: ResearchUser = {
  id: 0,
  name: "Preview analyst",
  handle: "preview",
  role: "admin",
};

export function ResearchAuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<ResearchUser | null>(isResearchPreview ? PREVIEW_USER : null);
  const [loading, setLoading] = useState(!isResearchPreview);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isResearchPreview) return;
    researchApi
      .restore()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  const value = useMemo<ResearchAuthState>(
    () => ({
      user,
      loading,
      error,
      async login(identifier, password) {
        setError(null);
        try {
          const authenticated = await researchApi.login(identifier, password);
          setUser(authenticated);
        } catch (reason) {
          const message = reason instanceof Error ? reason.message : "Login failed";
          setError(message);
          throw reason;
        }
      },
      async logout() {
        if (!isResearchPreview) await researchApi.logout();
        setUser(null);
      },
    }),
    [error, loading, user],
  );

  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useResearchAuth(): ResearchAuthState {
  const value = useContext(Context);
  if (!value) throw new Error("useResearchAuth must be used inside ResearchAuthProvider");
  return value;
}
