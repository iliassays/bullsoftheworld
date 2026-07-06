import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { type Lang, useLang } from "../lib/i18n";

// Per-page head management for the client-rendered SPA: title, description, canonical, hreflang,
// Open Graph / Twitter, JSON-LD. Design: ONE <SeoHead> (mounted by SeoProvider) imperatively
// upserts the head from the current route + whatever a page pushed via useSeo({...}). This is the
// belt-and-suspenders layer for Google's JS-rendering pass; the API /seo renderer (served to
// bots/social scrapers that never run JS) is the primary SEO surface.
//
// Imperative (not react-helmet-async): helmet-async v2 silently committed nothing under Vite dev +
// StrictMode here, and a ~40-line upsert we control is more predictable than debugging its
// internals — it updates the SAME static tags already in index.html in place, so no duplicates.

export const SITE = "https://bullsofdhaka.com";

type Loc = string | Record<Lang, string>;
export interface SeoValues {
  title?: Loc;
  description?: Loc;
  image?: string;
  noindex?: boolean;
  jsonLd?: object | object[];
}

const DEFAULT_TITLE: Record<Lang, string> = {
  bn: "Bulls of Dhaka — ঢাকা স্টক এক্সচেঞ্জের তথ্য, গুজব নয়",
  en: "Bulls of Dhaka — Dhaka Stock Exchange data, not rumours",
};
const DEFAULT_DESC: Record<Lang, string> = {
  bn: "DSE-র শেয়ারের দাম, ফান্ডামেন্টাল, চার্ট প্যাটার্ন ও কমিউনিটি — এক জায়গায়। বর্ণনামূলক তথ্য, বিনিয়োগ পরামর্শ নয়।",
  en: "DSE share prices, fundamentals, chart patterns and community — in one place. Descriptive data, not investment advice.",
};

function pick(v: Loc | undefined, lang: Lang): string | undefined {
  if (v == null) return undefined;
  return typeof v === "string" ? v : v[lang];
}
function stripLang(pathname: string): string {
  return pathname.replace(/^\/(bn|en)(?=\/|$)/, "") || "/";
}

export function siteJsonLd(): object[] {
  return [
    { "@context": "https://schema.org", "@type": "Organization", name: "Bulls of Dhaka", url: SITE, logo: `${SITE}/logo-mark-v2.png` },
    {
      "@context": "https://schema.org",
      "@type": "WebSite",
      name: "Bulls of Dhaka",
      url: SITE,
      potentialAction: {
        "@type": "SearchAction",
        target: `${SITE}/bn/s/{search_term_string}`,
        "query-input": "required name=search_term_string",
      },
    },
  ];
}

export function breadcrumbJsonLd(lang: Lang, trail: { name: string; path: string }[]): object {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: trail.map((c, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: c.name,
      item: `${SITE}/${lang}${c.path === "/" ? "" : c.path}`,
    })),
  };
}

// --- imperative head upsert helpers -----------------------------------------------------------
function upsertMeta(attr: "name" | "property", key: string, content: string) {
  let el = document.head.querySelector<HTMLMetaElement>(`meta[${attr}="${key}"]`);
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute(attr, key);
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
}
function upsertLink(rel: string, hreflang: string | null, href: string) {
  const sel = hreflang ? `link[rel="${rel}"][hreflang="${hreflang}"]` : `link[rel="${rel}"]`;
  let el = document.head.querySelector<HTMLLinkElement>(sel);
  if (!el) {
    el = document.createElement("link");
    el.setAttribute("rel", rel);
    if (hreflang) el.setAttribute("hreflang", hreflang);
    document.head.appendChild(el);
  }
  el.setAttribute("href", href);
}
function removeMeta(attr: "name" | "property", key: string) {
  document.head.querySelector(`meta[${attr}="${key}"]`)?.remove();
}

const SeoCtx = createContext<{ set: (v: SeoValues | null) => void }>({ set: () => {} });

export function SeoProvider({ children }: { children: ReactNode }) {
  const [values, setValues] = useState<SeoValues | null>(null);
  const setterRef = useRef((v: SeoValues | null) => setValues(v));
  return (
    <SeoCtx.Provider value={{ set: setterRef.current }}>
      <SeoHead values={values} />
      {children}
    </SeoCtx.Provider>
  );
}

// Pages call this to set their head; resets to site defaults on unmount / when values change.
export function useSeo(v: SeoValues) {
  const { set } = useContext(SeoCtx);
  const key = JSON.stringify(v);
  useEffect(() => {
    set(v);
    return () => set(null);
    // key captures v; set is stable (ref-backed)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
}

function SeoHead({ values }: { values: SeoValues | null }) {
  const { lang } = useLang();
  const loc = useLocation();
  const v = values ?? {};
  const suffix = stripLang(loc.pathname) === "/" ? "" : stripLang(loc.pathname);
  const canonical = `${SITE}/${lang}${suffix}`;
  const altBn = `${SITE}/bn${suffix}`;
  const altEn = `${SITE}/en${suffix}`;
  const t = pick(v.title, lang) ?? DEFAULT_TITLE[lang];
  const d = pick(v.description, lang) ?? DEFAULT_DESC[lang];
  const img = v.image ?? `${SITE}/og.png`;
  const jsonLd = v.jsonLd ? (Array.isArray(v.jsonLd) ? v.jsonLd : [v.jsonLd]) : [];
  const jsonLdStr = JSON.stringify(jsonLd);

  useEffect(() => {
    document.title = t;
    document.documentElement.lang = lang;
    upsertMeta("name", "description", d);
    upsertLink("canonical", null, canonical);
    upsertLink("alternate", "bn", altBn);
    upsertLink("alternate", "en", altEn);
    upsertLink("alternate", "x-default", altBn);
    upsertMeta("property", "og:title", t);
    upsertMeta("property", "og:description", d);
    upsertMeta("property", "og:url", canonical);
    upsertMeta("property", "og:image", img);
    upsertMeta("name", "twitter:title", t);
    upsertMeta("name", "twitter:description", d);
    upsertMeta("name", "twitter:image", img);
    if (v.noindex) upsertMeta("name", "robots", "noindex,follow");
    else removeMeta("name", "robots");
    // JSON-LD: replace our managed blocks each render.
    document.head.querySelectorAll("script[data-seo-jsonld]").forEach((e) => e.remove());
    for (const block of jsonLd) {
      const s = document.createElement("script");
      s.type = "application/ld+json";
      s.setAttribute("data-seo-jsonld", "");
      s.textContent = JSON.stringify(block);
      document.head.appendChild(s);
    }
  }, [t, d, canonical, altBn, altEn, img, lang, v.noindex, jsonLdStr]);

  return null;
}
