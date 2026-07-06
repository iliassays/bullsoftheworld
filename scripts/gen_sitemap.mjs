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

const SITE = "https://bullsofdhaka.com";
const API = process.env.PROD_API_URL || "https://api.bullsofdhaka.com";
const LANGS = ["bn", "en"];
const PATTERN_TYPES = [
  "ascending_triangle",
  "descending_triangle",
  "channel_up",
  "channel_down",
  "channel_horizontal",
  "double_top",
  "double_bottom",
];

const STATIC_PATHS = [
  "/",
  "/markets",
  "/ideas",
  "/learn/patterns",
  "/about",
  ...PATTERN_TYPES.map((t) => `/learn/patterns/${t}`),
];

async function stockPaths() {
  try {
    const res = await fetch(`${API}/symbols?limit=500`);
    if (!res.ok) throw new Error(`/symbols HTTP ${res.status}`);
    const list = await res.json();
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
    `    <xhtml:link rel="alternate" hreflang="x-default" href="${abs("bn", path)}"/>`,
  ].join("\n");
  return LANGS.map((lang) => `  <url>\n    <loc>${abs(lang, path)}</loc>\n${alts}\n  </url>`).join("\n");
}

const paths = [...STATIC_PATHS, ...(await stockPaths())];
const xml =
  `<?xml version="1.0" encoding="UTF-8"?>\n` +
  `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\n` +
  paths.map(urlEntries).join("\n") +
  `\n</urlset>\n`;

const out = join(dirname(fileURLToPath(import.meta.url)), "..", "apps", "web", "dist", "sitemap.xml");
writeFileSync(out, xml);
console.log(
  `sitemap: ${paths.length} paths × ${LANGS.length} langs = ${paths.length * LANGS.length} urls → ${out}`,
);
