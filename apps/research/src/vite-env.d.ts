/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_RESEARCH_API_URL?: string;
  readonly VITE_RESEARCH_SITE_URL?: string;
  readonly VITE_RESEARCH_PORTAL_URL?: string;
  readonly VITE_RESEARCH_TENANT?: "bullsofdhaka" | "bullsofwallst";
  readonly VITE_RESEARCH_MARKET?: "DSE" | "US";
  readonly VITE_RESEARCH_PREVIEW?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
