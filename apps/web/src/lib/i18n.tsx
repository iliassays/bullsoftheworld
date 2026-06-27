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
