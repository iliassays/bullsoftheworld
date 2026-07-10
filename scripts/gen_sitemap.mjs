#!/usr/bin/env node
// Generate apps/web/dist/sitemap.xml from the live /symbols API + the static public routes, each
// emitted for both languages with hreflang alternates. Run from deploy-prod.sh AFTER the vite
// build (so dist/ exists) and BEFORE the S3 root-files sync (which uploads it).
//
// The symbol universe changes rarely, so build-time freshness is fine. If the API is unreachable
// the script still writes a valid sitemap of the static routes rather than failing the deploy.
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const SITE = (process.env.WEB_SITE_URL || process.env.PROD_SITE_URL || "https://bullsofdhaka.com").replace(
  /\/$/,
  "",
);
const API = process.env.WEB_API_URL || process.env.PROD_API_URL || "https://api.bullsofdhaka.com";
const TENANT_HOST = process.env.WEB_TENANT_HOST || new URL(SITE).hostname;
const DEFAULT_LANG = process.env.WEB_DEFAULT_LANG || "bn";
const LANGS = (process.env.WEB_LANGS || "bn,en")
  .split(",")
  .map((lang) => lang.trim())
  .filter(Boolean);
const BRAND_NAME = process.env.WEB_BRAND_NAME || "Bulls of Dhaka";
const PATTERN_TYPES = [
  "ascending_triangle",
  "descending_triangle",
  "channel_up",
  "channel_down",
  "channel_horizontal",
  "double_top",
  "double_bottom",
];

async function staticPaths() {
  const base = ["/", "/about"];
  try {
    const res = await fetch(`${API}/market/config`, {
      headers: { "X-Tenant-Host": TENANT_HOST },
    });
    if (!res.ok) throw new Error(`/market/config HTTP ${res.status}`);
    const config = await res.json();
    if (config.features?.curated_screens) {
      base.push(
        "/markets",
        "/ideas",
        "/learn/patterns",
        ...PATTERN_TYPES.map((t) => `/learn/patterns/${t}`),
      );
    }
  } catch (e) {
    console.warn(`⚠ could not fetch market capabilities (${e.message}) — sitemap will stay conservative`);
  }
  return base;
}

async function stockPaths() {
  try {
    const list = [];
    const limit = 500;
    for (let offset = 0; ; offset += limit) {
      const res = await fetch(`${API}/symbols?limit=${limit}&offset=${offset}`, {
        headers: { "X-Tenant-Host": TENANT_HOST },
      });
      if (!res.ok) throw new Error(`/symbols HTTP ${res.status}`);
      const page = await res.json();
      list.push(...page);
      if (page.length < limit) break;
    }
    // Encode the code: some real DSE tickers contain XML/URL-unsafe chars (e.g. "KAY&QUE").
    return list.map((s) => `/s/${encodeURIComponent(s.code)}`);
  } catch (e) {
    console.warn(`⚠ could not fetch symbols (${e.message}) — sitemap will list static routes only`);
    return [];
  }
}

const abs = (lang, path) => `${SITE}/${lang}${path === "/" ? "" : path}`;

function urlEntries(path) {
  // One <url> per language; each carries the full hreflang alternate set (bn, en, x-default=bn).
  const alts = [
    ...LANGS.map((l) => `    <xhtml:link rel="alternate" hreflang="${l}" href="${abs(l, path)}"/>`),
    `    <xhtml:link rel="alternate" hreflang="x-default" href="${abs(DEFAULT_LANG, path)}"/>`,
  ].join("\n");
  return LANGS.map((lang) => `  <url>\n    <loc>${abs(lang, path)}</loc>\n${alts}\n  </url>`).join("\n");
}

const paths = [...(await staticPaths()), ...(await stockPaths())];
const xml =
  `<?xml version="1.0" encoding="UTF-8"?>\n` +
  `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\n` +
  paths.map(urlEntries).join("\n") +
  `\n</urlset>\n`;

const out = join(dirname(fileURLToPath(import.meta.url)), "..", "apps", "web", "dist", "sitemap.xml");
writeFileSync(out, xml);
const robotsOut = join(dirname(fileURLToPath(import.meta.url)), "..", "apps", "web", "dist", "robots.txt");
writeFileSync(
  robotsOut,
  `# ${BRAND_NAME} — allow public pages, keep private/personal + transient auth pages out.
User-agent: *
Allow: /
Disallow: /*/portfolio
Disallow: /*/alerts
Disallow: /*/watchlist
Disallow: /*/me
Disallow: /*/cockpit
Disallow: /*/welcome
Disallow: /*/forgot
Disallow: /*/reset
Disallow: /*/verify
Disallow: /*/u/

Sitemap: ${SITE}/sitemap.xml
`,
);
console.log(
  `sitemap: ${paths.length} paths × ${LANGS.length} langs = ${paths.length * LANGS.length} urls → ${out}`,
);
console.log(`robots: ${robotsOut}`);
