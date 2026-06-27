import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

// Bilingual portal: English + Bangla. The selection is persisted in localStorage and sent to the
// API as `X-Locale` so generated/dynamic content (Weekend Review, digest, levels, explainer…) comes
// back in the same language. Static UI strings live in STRINGS and resolve via t().
export type Lang = "en" | "bn";
const KEY = "bulls.lang";
const SUPPORTED: Lang[] = ["en", "bn"];

function readStored(): Lang {
  try {
    const v = localStorage.getItem(KEY) as Lang | null;
    if (v && SUPPORTED.includes(v)) return v;
  } catch {
    /* localStorage unavailable */
  }
  return "bn"; // Bangla-first default
}

// Module-level mirror so non-React code (the API request()) can read the current language.
let _lang: Lang = readStored();
export const currentLang = (): Lang => _lang;

type Entry = { en: string; bn: string };
const STRINGS: Record<string, Entry> = {
  tagline: { en: "Facts, not rumours", bn: "তথ্যে চলুন, গুজবে নয়" },
  delayed: { en: "Delayed", bn: "বিলম্বিত" },
  "nav.feed": { en: "Feed", bn: "ফিড" },
  "nav.markets": { en: "Markets", bn: "মার্কেট" },
  "nav.bulls": { en: "Bulls", bn: "বুলস" },
  "nav.watch": { en: "Watch", bn: "ওয়াচ" },
  "nav.me": { en: "Me", bn: "আমি" },
  "search.placeholder": {
    en: "Search ticker… e.g. GP, Grameenphone",
    bn: "টিকার খুঁজুন… যেমন GP, গ্রামীণফোন",
  },
  // Symbol page — tabs
  "tab.overview": { en: "Overview", bn: "সারসংক্ষেপ" },
  "tab.feed": { en: "Feed", bn: "ফিড" },
  "tab.bulls": { en: "Bulls", bn: "বুলস" },
  "tab.news": { en: "News", bn: "খবর" },
  "tab.fundamentals": { en: "Fundamentals", bn: "ফান্ডামেন্টাল" },
  "tab.ownership": { en: "Ownership", bn: "মালিকানা" },
  "tab.earnings": { en: "Earnings", bn: "আয়" },
  // Symbol page — quick stats + tags
  "stat.mktCap": { en: "Mkt Cap", bn: "বাজার মূলধন" },
  "stat.vol": { en: "Vol", bn: "ভলিউম" },
  "stat.pe": { en: "P/E", bn: "পি/ই" },
  "stat.eps": { en: "EPS", bn: "ইপিএস" },
  "stat.freeFloat": { en: "Free float", bn: "ফ্রি ফ্লোট" },
  "tag.cheaperSector": { en: "cheaper than sector", bn: "খাতের চেয়ে সস্তা" },
  "tag.pricierSector": { en: "pricier than sector", bn: "খাতের চেয়ে দামি" },
  "tag.inlineSector": { en: "in line", bn: "খাতের সমান" },
  normal: { en: "normal", bn: "স্বাভাবিক" },
  // Symbol page — header
  watching: { en: "watching", bn: "জন দেখছে" },
  thisWeek: { en: "this week", bn: "এই সপ্তাহে" },
  "btn.watch": { en: "☆ Watch", bn: "☆ ওয়াচ" },
  "btn.watching": { en: "★ Watching", bn: "★ ওয়াচড" },
  noQuote: { en: "No quote yet.", bn: "এখনো কোনো দর নেই।" },
  delayedAsOf: { en: "delayed · as of", bn: "বিলম্বিত · সর্বশেষ" },
  attentionRising: { en: "Attention rising", bn: "আলোচনা বাড়ছে" },
  usualChatter: { en: "usual chatter", bn: "স্বাভাবিক আলোচনা" },
  // Range bar
  "range.52w": { en: "52-week range", bn: "৫২-সপ্তাহের পরিসর" },
  "range.nearHigh": { en: "near high", bn: "চূড়ার কাছে" },
  "range.nearLow": { en: "near low", bn: "তলানির কাছে" },
  "range.mid": { en: "mid-range", bn: "মাঝামাঝি" },
};

interface I18n {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: string) => string;
}
const Ctx = createContext<I18n>({ lang: _lang, setLang: () => {}, t: (k) => k });

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(_lang);
  useEffect(() => {
    _lang = lang;
    try {
      localStorage.setItem(KEY, lang);
    } catch {
      /* ignore */
    }
    document.documentElement.lang = lang;
  }, [lang]);
  const t = (key: string) => STRINGS[key]?.[lang] ?? key;
  return <Ctx.Provider value={{ lang, setLang: setLangState, t }}>{children}</Ctx.Provider>;
}

export const useLang = () => useContext(Ctx);
