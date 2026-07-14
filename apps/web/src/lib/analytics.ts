import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { api } from "./api";

// First-party route and feature events go to the tenant-scoped API; GA/GTM (see index.html)
// tracks in parallel.

const ATTRIBUTION_KEY = "bulls.attribution";
const SERVER_PROPERTY_KEYS = new Set([
  "activation_target",
  "activation_version",
  "alert_kind",
  "board_key",
  "campaign",
  "destination",
  "direction",
  "evaluation",
  "market",
  "medium",
  "query_length",
  "question_kind",
  "result_rank",
  "source",
  "stock_code",
  "step",
  "strategy_pack",
  "surface",
  "watch_count",
]);

function attribution(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const query = new URLSearchParams(window.location.search);
  const incoming = {
    source: query.get("utm_source") ?? "",
    medium: query.get("utm_medium") ?? "",
    campaign: query.get("utm_campaign") ?? "",
  };
  if (incoming.source || incoming.medium || incoming.campaign) {
    try {
      sessionStorage.setItem(ATTRIBUTION_KEY, JSON.stringify(incoming));
    } catch {
      // Storage can be unavailable in strict privacy modes; events still work without attribution.
    }
    return incoming;
  }
  try {
    return JSON.parse(sessionStorage.getItem(ATTRIBUTION_KEY) ?? "{}") as Record<string, string>;
  } catch {
    return {};
  }
}

function serverProperties(
  params: Record<string, string | number | boolean | null | undefined>,
) {
  const merged = { ...attribution(), ...params };
  return Object.fromEntries(
    Object.entries(merged).filter(
      ([key, value]) => SERVER_PROPERTY_KEYS.has(key) && value !== undefined,
    ),
  );
}

export function trackProductEvent(
  name: string,
  params: Record<string, string | number | boolean | null | undefined> = {},
) {
  return api
    .productEvent(name, serverProperties(params))
    .then(() => undefined)
    .catch(() => undefined);
}

// /{bn|en}/s/{CODE} → CODE (uppercased); null for any other route.
function stockCodeFromPath(pathname: string): string | null {
  const m = pathname.match(/^\/(?:bn|en)\/s\/([^/]+)/);
  return m ? decodeURIComponent(m[1]).toUpperCase() : null;
}

export function usePageViewTracking(enabled: boolean) {
  const loc = useLocation();
  useEffect(() => {
    if (!enabled) return;
    const code = stockCodeFromPath(loc.pathname);
    trackProductEvent("page_view", {
      surface: code ? "symbol" : "route",
      stock_code: code ?? undefined,
    });
  }, [enabled, loc.pathname, loc.search]);
}
