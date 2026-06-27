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
  // Markets page chrome
  "markets.searchPlaceholder": { en: "Search a code, e.g. GP → Enter", bn: "কোড লিখুন, যেমন GP → এন্টার" },
  "markets.lookingFor": { en: "What are you looking for?", bn: "আপনি কী খুঁজছেন?" },
  "markets.browseAll": { en: "Browse every board, grouped.", bn: "সব বোর্ড দেখুন, গ্রুপ অনুযায়ী।" },
  "markets.footer": {
    en: "Computed from end-of-day prices · descriptive screens, not recommendations.",
    bn: "দিনশেষের দাম থেকে গণনা · তথ্যমূলক স্ক্রিন, সুপারিশ নয়।",
  },
  viewMore: { en: "View more →", bn: "আরও দেখুন →" },
  "col.symbol": { en: "Symbol", bn: "টিকার" },
  "col.price": { en: "Price", bn: "দাম" },
  nothingHere: { en: "Nothing here right now.", bn: "এই মুহূর্তে কিছু নেই।" },
  "screen.descNote": { en: "Descriptive screen — not a recommendation.", bn: "তথ্যমূলক স্ক্রিন — সুপারিশ নয়।" },
  backToMarkets: { en: "← Markets", bn: "← মার্কেট" },
  "explore.moverReversal": {
    en: "1-month moves often reverse. For a lasting trend, see “Strongest trend”.",
    bn: "১-মাসের মুভ প্রায়ই উল্টে যায়। টেকসই প্রবণতার জন্য “সবচেয়ে শক্তিশালী প্রবণতা” দেখুন।",
  },
  "explore.dotsNote": {
    en: "Dots = climbing over 3M·6M·12M (green = strong). All three green means the uptrend is broad, not just recent.",
    bn: "ডট = ৩M·৬M·১২M-এ উঠছে (সবুজ = শক্তিশালী)। তিনটিই সবুজ মানে প্রবণতা ব্যাপক, শুধু সাম্প্রতিক নয়।",
  },
  // Lens chips
  "lens.all": { en: "All", bn: "সব" },
  "lens.momentum": { en: "Momentum", bn: "মোমেন্টাম" },
  "lens.value": { en: "Value", bn: "ভ্যালু" },
  "lens.dividend": { en: "Dividend", bn: "লভ্যাংশ" },
  "lens.steady": { en: "Steady", bn: "স্থির" },
  "lens.momentum.blurb": {
    en: "Stocks moving and trending — for traders who want strength.",
    bn: "যেসব শেয়ার নড়ছে ও প্রবণতায় আছে — শক্তি খোঁজা ট্রেডারদের জন্য।",
  },
  "lens.value.blurb": {
    en: "Cheap, profitable, growing — for bargain hunters.",
    bn: "সস্তা, লাভজনক, বর্ধনশীল — দরদাম খোঁজাদের জন্য।",
  },
  "lens.dividend.blurb": { en: "Cash payers — for income seekers.", bn: "নগদ লভ্যাংশদাতা — আয়-সন্ধানীদের জন্য।" },
  "lens.steady.blurb": {
    en: "Low-swing, quality names — for a calmer ride.",
    bn: "কম ওঠানামা, মানসম্পন্ন — শান্ত যাত্রার জন্য।",
  },
  // Group labels
  "group.movers": { en: "Movers", bn: "মুভার" },
  "group.community": { en: "Community", bn: "কমিউনিটি" },
  "group.value": { en: "Value & income", bn: "ভ্যালু ও আয়" },
  "group.technical": { en: "Technical", bn: "টেকনিক্যাল" },
  // Metric column headers
  "mh.moneyFlow": { en: "Money flow", bn: "মানি ফ্লো" },
  "mh.momentum": { en: "Momentum", bn: "মোমেন্টাম" },
  "mh.volume": { en: "Volume", bn: "ভলিউম" },
  "mh.yield": { en: "Yield", bn: "ইল্ড" },
  "mh.vsSector": { en: "vs sector", bn: "খাতের তুলনায়" },
  "mh.epsGrowth": { en: "EPS growth", bn: "ইপিএস বৃদ্ধি" },
  "mh.watchers": { en: "Watchers", bn: "ওয়াচার" },
  "mh.posts": { en: "Posts", bn: "পোস্ট" },
  "mh.turnover": { en: "Turnover", bn: "টার্নওভার" },
  "mh.bigMoney": { en: "Big money", bn: "বড় টাকা" },
  "mh.trend": { en: "Trend", bn: "প্রবণতা" },
  "mh.vsDsex": { en: "vs DSEX", bn: "DSEX-এর তুলনায়" },
  "mh.volatility": { en: "Volatility", bn: "অস্থিরতা" },
  "mh.change": { en: "Change", bn: "পরিবর্তন" },
  // Metric chip words
  "mc.strongInflow": { en: "Strong inflow", bn: "জোরালো প্রবাহ" },
  "mc.inflow": { en: "Inflow", bn: "অর্থ ঢুকছে" },
  "mc.strongOutflow": { en: "Strong outflow", bn: "জোরালো বহিঃপ্রবাহ" },
  "mc.outflow": { en: "Outflow", bn: "অর্থ বেরোচ্ছে" },
  "mc.flatFlow": { en: "Flat flow", bn: "স্থির প্রবাহ" },
  "mc.overbought": { en: "Overbought zone", bn: "অতিরিক্ত কেনা অঞ্চল" },
  "mc.oversold": { en: "Oversold zone", bn: "অতিরিক্ত বিক্রি অঞ্চল" },
  "mc.strongMomentum": { en: "Strong momentum", bn: "শক্তিশালী মোমেন্টাম" },
  "mc.weakMomentum": { en: "Weak momentum", bn: "দুর্বল মোমেন্টাম" },
  "mc.neutral": { en: "Neutral", bn: "নিরপেক্ষ" },
  "mc.veryHeavy": { en: "Very heavy", bn: "অত্যন্ত ভারী" },
  "mc.heavyVolume": { en: "Heavy volume", bn: "ভারী ভলিউম" },
  "mc.active": { en: "Active", bn: "সক্রিয়" },
  "mc.highYield": { en: "High yield", bn: "উচ্চ ইল্ড" },
  "mc.paysDividend": { en: "Pays dividend", bn: "লভ্যাংশ দেয়" },
  "mc.cheaperPeers": { en: "Cheaper than peers", bn: "সমকক্ষদের চেয়ে সস্তা" },
  "mc.fastGrowth": { en: "Fast growth", bn: "দ্রুত বৃদ্ধি" },
  "mc.growing": { en: "Growing", bn: "বর্ধনশীল" },
  "mc.accumulating": { en: "Accumulating", bn: "জমছে" },
  "mc.buying": { en: "Buying", bn: "কেনা হচ্ছে" },
  "mc.highlyProfitable": { en: "Highly profitable", bn: "অত্যন্ত লাভজনক" },
  "mc.profitable": { en: "Profitable", bn: "লাভজনক" },
  "mc.verySteady": { en: "Very steady", bn: "খুব স্থির" },
  "mc.steady": { en: "Steady", bn: "স্থির" },
  "mc.outperforming": { en: "Outperforming", bn: "বাজারকে ছাড়িয়ে" },
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
