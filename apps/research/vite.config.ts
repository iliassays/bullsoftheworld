import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

const BUILD_BOUNDARIES = {
  bullsofdhaka: {
    market: "DSE",
    siteHost: "research.bullsofdhaka.com",
    portalHost: "bullsofdhaka.com",
    apiHost: "api.bullsofdhaka.com",
  },
  bullsofwallst: {
    market: "US",
    siteHost: "research.bullsofwallst.com",
    portalHost: "bullsofwallst.com",
    apiHost: "api.bullsofwallst.com",
  },
} as const;

function httpsHost(value: string, name: string): string {
  const url = new URL(value);
  if (url.protocol !== "https:") throw new Error(`${name} must use HTTPS`);
  return url.hostname;
}

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  if (command === "build") {
    const tenant = env.VITE_RESEARCH_TENANT as keyof typeof BUILD_BOUNDARIES | undefined;
    const boundary = tenant ? BUILD_BOUNDARIES[tenant] : undefined;
    if (!boundary) {
      throw new Error("VITE_RESEARCH_TENANT must be bullsofdhaka or bullsofwallst");
    }
    if (env.VITE_RESEARCH_MARKET !== boundary.market) {
      throw new Error(`${tenant} research builds must use market ${boundary.market}`);
    }
    if (httpsHost(env.VITE_RESEARCH_SITE_URL, "VITE_RESEARCH_SITE_URL") !== boundary.siteHost) {
      throw new Error(`${tenant} research builds must use site ${boundary.siteHost}`);
    }
    if (httpsHost(env.VITE_RESEARCH_PORTAL_URL, "VITE_RESEARCH_PORTAL_URL") !== boundary.portalHost) {
      throw new Error(`${tenant} research builds must use portal ${boundary.portalHost}`);
    }
    if (httpsHost(env.VITE_RESEARCH_API_URL, "VITE_RESEARCH_API_URL") !== boundary.apiHost) {
      throw new Error(`${tenant} research builds must use API ${boundary.apiHost}`);
    }
  }

  return {
    plugins: [react()],
    build: {
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (!id.includes("/node_modules/")) return undefined;
            if (id.includes("/@tanstack/")) return "vendor-data";
            if (id.includes("/lucide-react/")) return "vendor-icons";
            if (id.includes("/lightweight-charts/")) return "vendor-chart";
            return "vendor-framework";
          },
        },
      },
    },
    server: { port: Number(process.env.PORT) || 5180 },
  };
});
