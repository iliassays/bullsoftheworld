import type { ResearchMarket } from "../features/research-queue/model";

export interface ResearchDeployment {
  tenant: "bullsofdhaka" | "bullsofwallst";
  market: ResearchMarket;
  brandName: string;
  exchangeName: string;
  siteUrl: string;
  siteAliases: readonly string[];
  portalUrl: string;
  portalLocale: "en";
  accountRecoveryUrl: string;
  apiUrl: string;
  tenantHost: string;
  currency: "BDT" | "USD";
  capTiers: readonly string[];
}

const DEPLOYMENTS: Record<ResearchDeployment["tenant"], ResearchDeployment> = {
  bullsofdhaka: {
    tenant: "bullsofdhaka",
    market: "DSE",
    brandName: "Bulls of Dhaka",
    exchangeName: "Dhaka Stock Exchange",
    siteUrl: "https://research.bullsofdhaka.com",
    siteAliases: ["https://atlas.bullsofdhaka.com"],
    portalUrl: "https://bullsofdhaka.com",
    portalLocale: "en",
    accountRecoveryUrl: "https://bullsofdhaka.com/en/forgot",
    apiUrl: "https://api.bullsofdhaka.com",
    tenantHost: "research.bullsofdhaka.com",
    currency: "BDT",
    capTiers: ["large", "mid", "small", "micro", "unclassified"],
  },
  bullsofwallst: {
    tenant: "bullsofwallst",
    market: "US",
    brandName: "Bulls of Wall Street",
    exchangeName: "U.S. equities",
    siteUrl: "https://research.bullsofwallst.com",
    siteAliases: ["https://atlas.bullsofwallst.com"],
    portalUrl: "https://bullsofwallst.com",
    portalLocale: "en",
    accountRecoveryUrl: "https://bullsofwallst.com/en/forgot",
    apiUrl: "https://api.bullsofwallst.com",
    tenantHost: "research.bullsofwallst.com",
    currency: "USD",
    capTiers: ["mega", "large", "mid", "small", "micro", "unclassified"],
  },
};

function inferredTenant(): ResearchDeployment["tenant"] {
  const hostname = typeof window === "undefined" ? "" : window.location.hostname.toLowerCase();
  if (hostname.includes("bullsofwallst")) return "bullsofwallst";
  return "bullsofdhaka";
}

function deployment(): ResearchDeployment {
  const tenant = (import.meta.env.VITE_RESEARCH_TENANT || inferredTenant()) as ResearchDeployment["tenant"];
  const profile = DEPLOYMENTS[tenant];
  if (!profile) throw new Error(`Unsupported research tenant: ${tenant}`);

  const configuredMarket = import.meta.env.VITE_RESEARCH_MARKET;
  if (configuredMarket && configuredMarket !== profile.market) {
    throw new Error(`Research tenant ${tenant} cannot be built for market ${configuredMarket}`);
  }

  const configuredSite = import.meta.env.VITE_RESEARCH_SITE_URL;
  const configuredPortal = import.meta.env.VITE_RESEARCH_PORTAL_URL;
  const configuredApi = import.meta.env.VITE_RESEARCH_API_URL;
  if (import.meta.env.PROD) {
    for (const [label, configured, expected] of [
      ["site", configuredSite, profile.siteUrl],
      ["portal", configuredPortal, profile.portalUrl],
      ["API", configuredApi, profile.apiUrl],
    ] as const) {
      if (!configured) continue;
      const actualUrl = new URL(configured);
      const expectedUrl = new URL(expected);
      if (actualUrl.protocol !== "https:" || actualUrl.hostname !== expectedUrl.hostname) {
        throw new Error(
          `Research ${label} ${configured} contradicts the ${tenant} deployment boundary`,
        );
      }
    }
    if (typeof window !== "undefined") {
      const allowedSiteHosts = [profile.siteUrl, ...profile.siteAliases].map(
        (url) => new URL(url).hostname,
      );
      if (!allowedSiteHosts.includes(window.location.hostname)) {
        throw new Error(
          `Host ${window.location.hostname} is outside the ${tenant} research deployment boundary`,
        );
      }
    }
  }
  const browserOrigin = typeof window === "undefined" ? null : window.location.origin;
  return {
    ...profile,
    siteUrl: configuredSite || (import.meta.env.DEV && browserOrigin ? browserOrigin : profile.siteUrl),
    portalUrl: configuredPortal || profile.portalUrl,
    apiUrl: configuredApi || (import.meta.env.DEV ? "http://127.0.0.1:8090" : profile.apiUrl),
  };
}

export const researchDeployment = deployment();
export const isResearchPreview = import.meta.env.VITE_RESEARCH_PREVIEW === "true";

export function buildPortalTickerUrl(
  portalUrl: string,
  locale: string,
  ticker: string,
): string {
  const normalizedTicker = ticker.trim().toUpperCase();
  if (!normalizedTicker) throw new Error("A ticker is required to build a portal link");
  const normalizedLocale = locale.trim().toLowerCase();
  if (!normalizedLocale) throw new Error("A locale is required to build a portal link");
  return new URL(
    `/${encodeURIComponent(normalizedLocale)}/s/${encodeURIComponent(normalizedTicker)}`,
    portalUrl,
  ).toString();
}

export function portalTickerUrl(ticker: string): string {
  return buildPortalTickerUrl(
    researchDeployment.portalUrl,
    researchDeployment.portalLocale,
    ticker,
  );
}

export function tenantRequestHeaders(): Record<string, string> {
  return { "X-Tenant-Host": researchDeployment.tenantHost };
}
