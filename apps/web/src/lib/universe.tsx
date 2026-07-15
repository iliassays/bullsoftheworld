import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { useTenantConfig } from "./tenant";
import {
  ALL_UNIVERSE,
  normalizeUniverseTier,
  universeStorageKey,
  type UniverseTier,
} from "./universe-policy";

interface UniverseContextValue {
  tier: UniverseTier;
  setTier: (tier: UniverseTier) => void;
}

const UniverseContext = createContext<UniverseContextValue>({
  tier: ALL_UNIVERSE,
  setTier: () => undefined,
});

function storedTier(tenant: string, available: readonly string[]): UniverseTier {
  try {
    return normalizeUniverseTier(localStorage.getItem(universeStorageKey(tenant)), available);
  } catch {
    return ALL_UNIVERSE;
  }
}

export function UniverseProvider({ children }: { children: ReactNode }) {
  const { config } = useTenantConfig();
  const availableKey = config.cap_tiers.join(",");
  const [tier, setTierState] = useState<UniverseTier>(() =>
    storedTier(config.tenant_name, config.cap_tiers),
  );

  useEffect(() => {
    setTierState(storedTier(config.tenant_name, config.cap_tiers));
  }, [availableKey, config.cap_tiers, config.tenant_name]);

  const setTier = useCallback(
    (next: UniverseTier) => {
      const normalized = normalizeUniverseTier(next, config.cap_tiers);
      setTierState(normalized);
      try {
        localStorage.setItem(universeStorageKey(config.tenant_name), normalized);
      } catch {
        // Storage can be unavailable in hardened/private browser contexts; in-memory scope remains.
      }
    },
    [config.cap_tiers, config.tenant_name],
  );

  const value = useMemo(() => ({ tier, setTier }), [setTier, tier]);
  return <UniverseContext.Provider value={value}>{children}</UniverseContext.Provider>;
}

export function useUniverse(): UniverseContextValue {
  return useContext(UniverseContext);
}
