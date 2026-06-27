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
  // Plain read card chrome
  "plainRead.title": { en: "What this means", bn: "এর অর্থ কী" },
  "plainRead.howTraders": { en: "How traders read this", bn: "ট্রেডাররা এটি যেভাবে পড়েন" },
  // Explain card
  "explain.title": { en: "Deeper analysis", bn: "গভীর বিশ্লেষণ" },
  "explain.aiPrefix": { en: "AI-generated from the", bn: "AI দ্বারা তৈরি —" },
  "explain.aiSuffix": {
    en: "close · educational, not advice.",
    bn: "এর ক্লোজ থেকে · শিক্ষামূলক, পরামর্শ নয়।",
  },
  // Key levels
  "levels.title": { en: "Key levels & what to watch", bn: "মূল লেভেল ও যা লক্ষ্য রাখবেন" },
  // Digest / community buzz
  "digest.title": { en: "Community buzz", bn: "কমিউনিটির আলোচনা" },
  "digest.show": { en: "Show what's happening", bn: "কী ঘটছে দেখুন" },
  "digest.loading": { en: "Reading the tape and the crowd…", bn: "দর ও আলোচনা পড়া হচ্ছে…" },
  "digest.error": { en: "Couldn't load the digest", bn: "ডাইজেস্ট লোড করা যায়নি" },
  "digest.footer": {
    en: "Built from delayed price + recent posts. Not financial advice.",
    bn: "বিলম্বিত দর ও সাম্প্রতিক পোস্ট থেকে তৈরি। আর্থিক পরামর্শ নয়।",
  },
  posts: { en: "posts", bn: "পোস্ট" },
  "mood.bullish": { en: "🐂 Bullish crowd", bn: "🐂 তেজি ভিড়" },
  "mood.bearish": { en: "🐻 Bearish crowd", bn: "🐻 মন্দা ভিড়" },
  "mood.mixed": { en: "↔ Mixed crowd", bn: "↔ মিশ্র ভিড়" },
  "mood.quiet": { en: "· Quiet", bn: "· শান্ত" },
  // Pulse
  "pulse.title": { en: "Pulse", bn: "পালস" },
  "pulse.subtitle": {
    en: "Community activity over the last 7 days.",
    bn: "গত ৭ দিনের কমিউনিটি কার্যকলাপ।",
  },
  "pulse.sentiment": { en: "Sentiment", bn: "মনোভাব" },
  "pulse.volume": { en: "Message volume", bn: "মেসেজ ভলিউম" },
  "pulse.participation": { en: "Participation", bn: "অংশগ্রহণ" },
  // Pulse value words (backend returns English; mapped here)
  "pv.bullish": { en: "Bullish", bn: "তেজি" },
  "pv.bearish": { en: "Bearish", bn: "মন্দা" },
  "pv.mixed": { en: "Mixed", bn: "মিশ্র" },
  "pv.low": { en: "Low", bn: "কম" },
  "pv.moderate": { en: "Moderate", bn: "মাঝারি" },
  "pv.high": { en: "High", bn: "বেশি" },
  "pv.quiet": { en: "Quiet", bn: "শান্ত" },
  "pv.neutral": { en: "Neutral", bn: "নিরপেক্ষ" },
  // Technicals
  "tech.title": { en: "Technicals", bn: "টেকনিক্যাল" },
  asOf: { en: "as of", bn: "সর্বশেষ" },
  close: { en: "close", bn: "ক্লোজ" },
  "tech.aboveBoth": { en: "Above 50 & 200-day average", bn: "৫০ ও ২০০-দিনের গড়ের উপরে" },
  "tech.belowBoth": { en: "Below 50 & 200-day average", bn: "৫০ ও ২০০-দিনের গড়ের নিচে" },
  "tech.mixedMa": { en: "Mixed vs moving averages", bn: "মুভিং এভারেজের মিশ্র অবস্থান" },
  "tech.momentum": { en: "Momentum (RSI 14)", bn: "মোমেন্টাম (RSI 14)" },
  "tech.volVs20": { en: "Volume vs 20-day", bn: "২০-দিনের তুলনায় ভলিউম" },
  "tech.nearestSupport": { en: "Nearest support", bn: "নিকটতম সাপোর্ট" },
  "tech.nearestResistance": { en: "Nearest resistance", bn: "নিকটতম রেজিস্ট্যান্স" },
  "rsi.elevated": { en: "elevated", bn: "উঁচু" },
  "rsi.depressed": { en: "depressed", bn: "নিচু" },
  "rsi.mid": { en: "mid-range", bn: "মাঝামাঝি" },
  "tech.fromHigh": { en: "from high", bn: "সর্বোচ্চ থেকে" },
  "tech.footer": {
    en: "Computed from end-of-day prices · descriptive, not advice.",
    bn: "দিনশেষের দাম থেকে গণনা · তথ্যমূলক, পরামর্শ নয়।",
  },
  // Candle chart
  "chart.support": { en: "Support", bn: "সাপোর্ট" },
  "chart.resistance": { en: "Resistance", bn: "রেজিস্ট্যান্স" },
  "chart.noHistory": { en: "No price history.", bn: "কোনো দামের ইতিহাস নেই।" },
  // Sectors
  "sectors.hot": { en: "Hot sectors today", bn: "আজকের গরম খাত" },
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
