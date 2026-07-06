import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

// Bilingual portal: English + Bangla. The selection is persisted in localStorage and sent to the
// API as `X-Locale` so generated/dynamic content (Weekend Review, digest, levels, explainer…) comes
// back in the same language. Static UI strings live in STRINGS and resolve via t().
export type Lang = "en" | "bn";
const KEY = "bulls.lang";
export const SUPPORTED: Lang[] = ["en", "bn"];

export function readStored(): Lang {
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
// URL-first: the language now lives in the path (/bn/…, /en/…), and history.pushState updates
// window.location synchronously on navigation — so reading the path here means the API's X-Locale
// header is always in sync with the current route, with no dependency on React effect ordering
// (this is what used to cause the "reverse language" refetch bug). Falls back to the stored
// preference before the router has mounted / for any unprefixed path.
export const currentLang = (): Lang => {
  if (typeof window !== "undefined") {
    const seg = window.location.pathname.split("/")[1];
    if (SUPPORTED.includes(seg as Lang)) return seg as Lang;
  }
  return _lang;
};

type Entry = { en: string; bn: string };
const STRINGS: Record<string, Entry> = {
  tagline: { en: "Facts, not rumours", bn: "তথ্যে চলুন, গুজবে নয়" },
  delayed: { en: "15-min delayed", bn: "১৫ মিনিট বিলম্বিত" },
  "nav.feed": { en: "Feed", bn: "ফিড" },
  "nav.home": { en: "Home", bn: "হোম" },
  "nav.ideas": { en: "Ideas", bn: "আইডিয়া" },
  "nav.portfolio": { en: "Portfolio", bn: "পোর্টফোলিও" },
  "nav.alerts": { en: "Alerts", bn: "অ্যালার্ট" },
  "nav.markets": { en: "Markets", bn: "মার্কেট" },
  "nav.bulls": { en: "Bulls", bn: "বুলস" },
  "nav.watch": { en: "Watch", bn: "ওয়াচ" },
  "nav.about": { en: "About", bn: "সম্পর্কে" },
  "nav.scanner": { en: "Scanner", bn: "স্ক্যানার" },
  "scanner.today": { en: "Today", bn: "আজ" },
  "scanner.value": { en: "Value", bn: "ভ্যালু" },
  "scanner.lens": { en: "Lens", bn: "লেন্স" },
  "scanner.watchlist": { en: "Watchlist", bn: "ওয়াচলিস্ট" },
  "scanner.scope": { en: "Scan", bn: "স্ক্যান" },
  "scanner.market": { en: "Whole market", bn: "পুরো বাজার" },
  "scanner.watched": { en: "My watchlist", bn: "আমার ওয়াচলিস্ট" },
  "scanner.empty": {
    en: "Nothing meets these scans right now — check back during the session.",
    bn: "এই মুহূর্তে কিছু মিলছে না — সেশনের সময় আবার দেখুন।",
  },
  "scanner.emptyWatched": {
    en: "None of your watched stocks match these scans right now.",
    bn: "আপনার ওয়াচলিস্টের কোনো শেয়ার এই মুহূর্তে মিলছে না।",
  },
  "nav.me": { en: "Me", bn: "আমি" },
  "home.earningsToday": { en: "Earnings today", bn: "আজকের আয়" },
  "home.earningsTodayEmpty": {
    en: "No earnings meetings today",
    bn: "আজ কোনো আয়-সংক্রান্ত সভা নেই",
  },
  // Alerts inbox
  "alerts.title": { en: "Alerts", bn: "অ্যালার্ট" },
  "alerts.subtitle": {
    en: "For stocks you watch or hold — data events, never advice.",
    bn: "আপনার ওয়াচ বা হোল্ড করা শেয়ারের জন্য — শুধুই ডেটা, পরামর্শ নয়।",
  },
  "alerts.empty": {
    en: "Nothing yet — watch a stock and its data events will land here.",
    bn: "এখনো কিছু নেই — শেয়ার ওয়াচ করলে তার ডেটা ইভেন্ট এখানে আসবে।",
  },
  "alerts.loginTitle": { en: "Alerts are personal", bn: "অ্যালার্ট ব্যক্তিগত" },
  "alerts.loginBody": {
    en: "Log in to get 52-week events, ownership changes and earnings dates for the stocks you follow.",
    bn: "লগইন করলে আপনার শেয়ারের ৫২-সপ্তাহ ইভেন্ট, মালিকানা পরিবর্তন ও আয়ের তারিখ পাবেন।",
  },
  // Portfolio
  "pf.title": { en: "Portfolio", bn: "পোর্টফোলিও" },
  "pf.subtitle": {
    en: "Manual entries · never linked to your broker",
    bn: "নিজে লেখা এন্ট্রি · আপনার ব্রোকারের সাথে কোনো সংযোগ নেই",
  },
  "pf.totalValue": { en: "Total value", bn: "মোট মূল্য" },
  "pf.today": { en: "today", bn: "আজ" },
  "pf.allTime": { en: "all time", bn: "সর্বমোট" },
  "pf.holdings": { en: "Holdings", bn: "হোল্ডিং" },
  "pf.growthTitle": { en: "Growth over time", bn: "সময়ের সাথে প্রবৃদ্ধি" },
  "pf.growthBuilding": {
    en: "We started tracking your portfolio's value today — come back tomorrow to see the trend build.",
    bn: "আজ থেকে আপনার পোর্টফোলিওর মূল্য ট্র্যাক করা শুরু হয়েছে — প্রবণতা দেখতে আগামীকাল আসুন।",
  },
  "pf.empty": {
    en: "No holdings yet — add what you own to see it valued with today's prices.",
    bn: "এখনো কোনো হোল্ডিং নেই — যা আছে যোগ করুন, আজকের দামে মূল্য দেখুন।",
  },
  "pf.addTitle": { en: "Add a holding", bn: "হোল্ডিং যোগ করুন" },
  "pf.codePh": { en: "Ticker e.g. GP", bn: "টিকার যেমন GP" },
  "pf.qtyPh": { en: "Quantity", bn: "পরিমাণ" },
  "pf.costPh": { en: "Avg buy price ৳", bn: "গড় কেনা দাম ৳" },
  "pf.save": { en: "Save", bn: "সংরক্ষণ" },
  "pf.cancel": { en: "Cancel", bn: "বাতিল" },
  "pf.invalid": {
    en: "Enter a ticker, a quantity and a buy price.",
    bn: "টিকার, পরিমাণ ও কেনা দাম দিন।",
  },
  "pf.unknownCode": {
    en: "Couldn't save — check the ticker code.",
    bn: "সংরক্ষণ হয়নি — টিকার কোডটি দেখুন।",
  },
  "pf.loginTitle": { en: "Track what you own", bn: "আপনার শেয়ার ট্র্যাক করুন" },
  "pf.loginBody": {
    en: "Log in to keep a private list of your holdings, valued with delayed prices.",
    bn: "লগইন করে আপনার হোল্ডিংয়ের ব্যক্তিগত তালিকা রাখুন, বিলম্বিত দামে মূল্যায়িত।",
  },
  "pf.disclaimer": {
    en: "Prices delayed 15 min. We describe your entries — we never advise, and we never see your broker account.",
    bn: "দাম ১৫ মিনিট বিলম্বিত। আমরা শুধু আপনার এন্ট্রি দেখাই — পরামর্শ দিই না, ব্রোকার অ্যাকাউন্টও দেখি না।",
  },
  "pf.alertSet": { en: "Alert set", bn: "অ্যালার্ট সেট করা" },
  "pf.setAlert": { en: "+ Set alert", bn: "+ অ্যালার্ট" },
  "pf.postAddPrompt": {
    en: "Bought it in real life? Get pinged if it moves.",
    bn: "বাস্তবে কিনেছেন? দাম নড়লে জানতে চান?",
  },
  "pf.notNow": { en: "Not now", bn: "এখন না" },
  // Daily quiz
  "quiz.title": { en: "Daily quiz", bn: "দৈনিক কুইজ" },
  "quiz.dayStreak": { en: "day streak", bn: "দিনের স্ট্রিক" },
  "quiz.pts": { en: "pts", bn: "পয়েন্ট" },
  "quiz.disclaimer": {
    en: "Points measure learning — never trading.",
    bn: "পয়েন্ট শেখার হিসাব — লেনদেনের নয়।",
  },
  // Onboarding (post-register welcome flow)
  "ob.step": { en: "Step", bn: "ধাপ" },
  "ob.skip": { en: "Skip for now", bn: "এখন থাক" },
  "ob.continue": { en: "Continue", bn: "পরের ধাপ" },
  "ob.finish": { en: "Done — take me in", bn: "শেষ — শুরু করি" },
  "ob.sectorsTitle": { en: "Which sectors interest you?", bn: "কোন সেক্টরে আগ্রহ?" },
  "ob.sectorsBody": {
    en: "Pick one or more — we'll build your feed around them.",
    bn: "এক বা একাধিক বাছুন — সেগুলো ঘিরেই আপনার ফিড সাজাব।",
  },
  "ob.stocksTitle": { en: "Watch a few stocks", bn: "কয়েকটি শেয়ার ওয়াচ করুন" },
  "ob.stocksBody": {
    en: "They'll show on your home screen, and their data events land in your alerts.",
    bn: "এগুলো আপনার হোমে দেখাবে, আর তাদের ডেটা ইভেন্ট অ্যালার্টে আসবে।",
  },
  "ob.desksTitle": { en: "Follow the official desks", bn: "অফিসিয়াল ডেস্ক ফলো করুন" },
  "ob.desksBody": {
    en: "Verified, automated, facts-only — they post when the data moves.",
    bn: "ভেরিফাইড, স্বয়ংক্রিয়, শুধুই তথ্য — ডেটা নড়লেই পোস্ট করে।",
  },
  "ob.noStocks": {
    en: "Pick a sector first to see its stocks.",
    bn: "শেয়ার দেখতে আগে একটি সেক্টর বাছুন।",
  },
  "ob.watch": { en: "Watch", bn: "ওয়াচ" },
  "ob.watching": { en: "Watching", bn: "ওয়াচ হচ্ছে" },
  "ob.follow": { en: "Follow", bn: "ফলো" },
  "ob.following": { en: "Following", bn: "ফলো হচ্ছে" },
  // Per-stock price alerts
  "pa.title": { en: "Price alerts", bn: "দামের অ্যালার্ট" },
  "pa.above": { en: "above", bn: "উপরে" },
  "pa.below": { en: "below", bn: "নিচে" },
  "pa.add": { en: "Set", bn: "সেট" },
  "pa.remove": { en: "remove", bn: "মুছুন" },
  "pa.none": {
    en: "No price alerts for this stock yet.",
    bn: "এই শেয়ারের জন্য এখনো কোনো দামের অ্যালার্ট নেই।",
  },
  "pa.triggered": { en: "triggered", bn: "ট্রিগার হয়েছে" },
  // Home feed filter chips (Bulls tab merged into Home)
  "feedchip.all": { en: "All", bn: "সব" },
  "feedchip.desks": { en: "🐂 Desks", bn: "🐂 ডেস্ক" },
  "feedchip.people": { en: "People", bn: "মানুষ" },
  // Watchlist, not holdings — was labelled "My stocks" until a user report (2026-07-04) pointed
  // out that read as portfolio. "portfolio" below is the genuinely holdings-scoped chip.
  "feedchip.myStocks": { en: "☆ Watchlist", bn: "☆ ওয়াচলিস্ট" },
  "feedchip.portfolio": { en: "💼 Portfolio", bn: "💼 পোর্টফোলিও" },
  "feedchip.allDesks": { en: "All desks", bn: "সব ডেস্ক" },
  "search.placeholder": {
    en: "Search ticker… e.g. GP, Grameenphone",
    bn: "টিকার খুঁজুন… যেমন GP, গ্রামীণফোন",
  },
  // Symbol page — tabs
  "tab.overview": { en: "Overview", bn: "সারসংক্ষেপ" },
  "tab.investorLens": { en: "Investor Lens", bn: "ইনভেস্টর লেন্স" },
  "tab.feed": { en: "Feed", bn: "ফিড" },
  "tab.community": { en: "Community", bn: "কমিউনিটি" },
  "tab.financials": { en: "Financials", bn: "ফাইন্যান্সিয়াল" },
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
  "btn.watchLogin": { en: "Log in to watch this stock", bn: "এই স্টক ওয়াচ করতে লগ ইন করুন" },
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
  "plainRead.howTraders": {
    en: "How traders read this",
    bn: "ট্রেডাররা এটি যেভাবে পড়েন",
  },
  // Explain card
  "explain.title": { en: "Deeper analysis", bn: "গভীর বিশ্লেষণ" },
  "explain.cta": { en: "Generate analysis", bn: "বিশ্লেষণ তৈরি করুন" },
  "explain.hint": {
    en: "An AI plain-language read of this stock's whole picture — generated when you ask.",
    bn: "এই শেয়ারের সামগ্রিক চিত্রের একটি AI সহজ-ভাষার বিশ্লেষণ — আপনি চাইলে তৈরি হয়।",
  },
  "explain.retry": { en: "Couldn't generate. Try again.", bn: "তৈরি করা যায়নি। আবার চেষ্টা করুন।" },
  "explain.aiPrefix": { en: "AI-generated from the", bn: "AI দ্বারা তৈরি —" },
  "explain.aiSuffix": {
    en: "close · educational, not advice.",
    bn: "এর ক্লোজ থেকে · শিক্ষামূলক, পরামর্শ নয়।",
  },
  // Key levels
  "levels.title": {
    en: "Key levels & what to watch",
    bn: "মূল লেভেল ও যা লক্ষ্য রাখবেন",
  },
  // Digest / community buzz
  "digest.title": { en: "Community buzz", bn: "কমিউনিটির আলোচনা" },
  "digest.show": { en: "Show what's happening", bn: "কী ঘটছে দেখুন" },
  "digest.loading": {
    en: "Reading the tape and the crowd…",
    bn: "দর ও আলোচনা পড়া হচ্ছে…",
  },
  "digest.error": {
    en: "Couldn't load the digest",
    bn: "ডাইজেস্ট লোড করা যায়নি",
  },
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
  "mkt.live": { en: "Live", bn: "লাইভ" },
  "mkt.open": { en: "Open", bn: "খোলা" },
  "mkt.closed": { en: "Closed", bn: "বন্ধ" },
  "mkt.preOpen": { en: "Pre-open", bn: "খোলার আগে" },
  "mkt.updated": { en: "updated", bn: "আপডেট" },
  "mktIntro.title": { en: "New here? How to read this page", bn: "নতুন? এই পেজ কীভাবে পড়বেন" },
  "mktIntro.p1": {
    en: "These are descriptive signals — what the data shows, not buy/sell tips.",
    bn: "এগুলো বর্ণনামূলক সংকেত — ডেটা যা দেখায়, কেনা-বেচার টিপস নয়।",
  },
  "mktIntro.p2": {
    en: "Tap the ⓘ on any board to learn what it means and how traders read it.",
    bn: "যেকোনো বোর্ডের ⓘ চাপুন — এর অর্থ ও ট্রেডাররা কীভাবে পড়েন জানতে।",
  },
  "mktIntro.p3": {
    en: "Always check WHY (the news) before deciding — and remember what each signal does NOT tell you.",
    bn: "সিদ্ধান্তের আগে সবসময় কারণ (খবর) যাচাই করুন — আর মনে রাখুন প্রতিটি সংকেত কী বলে না।",
  },
  "mktIntro.dismiss": { en: "Got it", bn: "বুঝেছি" },
  "mkt.rankNote": {
    en: "Rankings as of the last close · prices 15-min delayed",
    bn: "র‍্যাঙ্কিং সর্বশেষ ক্লোজ অনুযায়ী · দাম ১৫ মিনিট বিলম্বিত",
  },
  "marketPulse.title": { en: "Market pulse", bn: "মার্কেট পালস" },
  "marketPulse.subtitle": {
    en: "Regime first: index, breadth, turnover and sector leadership.",
    bn: "আগে বাজারের অবস্থা: সূচক, ব্রেডথ, টার্নওভার ও খাতের নেতৃত্ব।",
  },
  "marketPulse.turnover": { en: "Turnover", bn: "টার্নওভার" },
  "marketPulse.vs20d": { en: "vs 20D avg", bn: "২০D গড়ের তুলনায়" },
  "marketPulse.breadth": { en: "Breadth", bn: "ব্রেডথ" },
  "marketPulse.sectors": { en: "Sectors", bn: "খাত" },
  "marketPulse.weak": { en: "Weak", bn: "দুর্বল" },
  "marketPulse.footer": {
    en: "Market context, not a signal by itself.",
    bn: "বাজারের প্রেক্ষাপট, একা কোনো সংকেত নয়।",
  },
  "risk.risk_on": { en: "Risk-on", bn: "রিস্ক-অন" },
  "risk.mixed": { en: "Mixed", bn: "মিশ্র" },
  "risk.defensive": { en: "Defensive", bn: "ডিফেন্সিভ" },
  "liq.adtv": { en: "ADTV", bn: "ADTV" },
  "liq.size5": { en: "Order guide", bn: "অর্ডার গাইড" },
  "liq.cat": { en: "Cat", bn: "ক্যাট" },
  "liq.deep": { en: "Deep liquidity", bn: "গভীর লিকুইডিটি" },
  "liq.tradeable": { en: "Tradeable liquidity", bn: "লেনদেনযোগ্য লিকুইডিটি" },
  "liq.watchSize": { en: "Size-sensitive", bn: "অর্ডার সাইজে সতর্কতা" },
  "liq.thin": { en: "Thin liquidity", bn: "পাতলা লিকুইডিটি" },
  "liq.highRisk": { en: "High-risk liquidity", bn: "উচ্চ-ঝুঁকি লিকুইডিটি" },
  "liqGuide.title": {
    en: "Liquidity: can you enter and exit easily?",
    bn: "লিকুইডিটি: সহজে ঢোকা ও বের হওয়া যাবে?",
  },
  "liqGuide.compact": {
    en: "ADTV, order guide, and read labels explained with simple examples.",
    bn: "ADTV, অর্ডার গাইড, আর রিড লেবেল সহজ উদাহরণে বুঝুন।",
  },
  "liqGuide.open": { en: "See examples", bn: "উদাহরণ দেখুন" },
  "liqGuide.subtitle": {
    en: "Before buying, ask one simple question: if I need to sell later, will enough people be trading this share?",
    bn: "কেনার আগে একটি সহজ প্রশ্ন করুন: পরে বিক্রি করতে হলে এই শেয়ারে যথেষ্ট লেনদেন থাকবে তো?",
  },
  "liqGuide.adtvTitle": { en: "ADTV = how busy the stock usually is", bn: "ADTV = শেয়ারটি সাধারণত কতটা ব্যস্ত" },
  "liqGuide.adtvBody": {
    en: "ADTV tells how much money normally trades in this stock each day. We use the last 20 sessions: average volume x last close price. Bigger ADTV usually means buying and selling is easier.",
    bn: "ADTV দেখায় এই শেয়ারে প্রতিদিন সাধারণত কত টাকার লেনদেন হয়। আমরা শেষ ২০ সেশন ব্যবহার করি: গড় ভলিউম x সর্বশেষ ক্লোজ দাম। ADTV যত বড়, কেনা-বেচা সাধারণত তত সহজ।",
  },
  "liqGuide.orderTitle": { en: "Order guide = when your order starts becoming big", bn: "অর্ডার গাইড = আপনার অর্ডার কখন বড় হয়ে যাচ্ছে" },
  "liqGuide.orderBody": {
    en: "We show about 5% of ADTV as a simple warning line. Example: if ADTV is ৳8.5cr, then 5% is about ৳42L. It is not a target to buy. It means a larger order may need splitting, otherwise your own order can move the price.",
    bn: "আমরা ADTV-এর প্রায় ৫% একটি সহজ সতর্কতা লাইন হিসেবে দেখাই। উদাহরণ: ADTV ৳8.5cr হলে ৫% প্রায় ৳42L। এটি কেনার টার্গেট নয়। এর চেয়ে বড় অর্ডার হলে ভাগ করে দেওয়া লাগতে পারে, নাহলে আপনার অর্ডারেই দাম নড়তে পারে।",
  },
  "liqGuide.liquidExampleTitle": {
    en: "Story: easier trade",
    bn: "গল্প: তুলনামূলক সহজ ট্রেড",
  },
  "liqGuide.liquidExampleBody": {
    en: "You want to buy ৳2L. The stock normally trades about ৳8.5cr per day, and the order guide is ~৳42L. Your order is small compared with normal trading, so entry and exit are usually easier.",
    bn: "আপনি ৳2L কিনতে চান। শেয়ারটি দিনে সাধারণত প্রায় ৳8.5cr লেনদেন করে, আর অর্ডার গাইড ~৳42L। স্বাভাবিক লেনদেনের তুলনায় আপনার অর্ডার ছোট, তাই ঢোকা ও বের হওয়া সাধারণত সহজ।",
  },
  "liqGuide.thinExampleTitle": {
    en: "Story: risky trade",
    bn: "গল্প: ঝুঁকিপূর্ণ ট্রেড",
  },
  "liqGuide.thinExampleBody": {
    en: "You want to buy ৳5L. The stock normally trades only ৳20L per day, and the order guide is ~৳1L. Your order is 25% of a normal day. You may push the price up while buying, then struggle to sell later.",
    bn: "আপনি ৳5L কিনতে চান। শেয়ারটি দিনে সাধারণত মাত্র ৳20L লেনদেন করে, আর অর্ডার গাইড ~৳1L। আপনার অর্ডার স্বাভাবিক দিনের ২৫%। কিনতে গিয়ে দাম বাড়িয়ে ফেলতে পারেন, পরে বিক্রি করাও কঠিন হতে পারে।",
  },
  "liqGuide.setupTitle": {
    en: "What the read labels mean",
    bn: "রিড লেবেলগুলোর মানে",
  },
  "liqGuide.setupBody": {
    en: "Clean read means the signal has liquidity and supporting context. Mixed read means something looks interesting, but you should confirm with news and chart. High-risk read means thin trading, Z category, or pump-like behavior.",
    bn: "Clean read মানে সংকেতের সাথে লিকুইডিটি ও সহায়ক কারণ আছে। Mixed read মানে কিছু আকর্ষণীয়, তবে খবর ও চার্ট দিয়ে নিশ্চিত করা দরকার। High-risk read মানে পাতলা লেনদেন, Z category, বা pump-like আচরণ।",
  },
  "liqGuide.setupCleanBody": {
    en: "The signal has enough liquidity and supporting context, such as institutional/foreign buying, quality, dividend, relative strength, or material news.",
    bn: "সংকেতের সাথে পর্যাপ্ত লিকুইডিটি ও সহায়ক কারণ আছে — যেমন প্রতিষ্ঠান/বিদেশি কেনা, মান, ডিভিডেন্ড, বাজারের চেয়ে শক্তি, বা গুরুত্বপূর্ণ খবর।",
  },
  "liqGuide.setupMixedBody": {
    en: "Something is interesting, but it needs confirmation. Check the latest news, chart level, volume, and whether the move is already stretched.",
    bn: "কিছু আকর্ষণীয় আছে, তবে নিশ্চিত করা দরকার। সর্বশেষ খবর, চার্টের লেভেল, ভলিউম, এবং মুভ বেশি দূর চলে গেছে কি না দেখুন।",
  },
  "liqGuide.setupRiskyBody": {
    en: "Be careful: thin trading, Z category, or pump-like behavior can make entry and exit difficult.",
    bn: "সতর্ক থাকুন: পাতলা লেনদেন, Z category, বা pump-like আচরণে ঢোকা ও বের হওয়া কঠিন হতে পারে।",
  },
  "liqGuide.footer": {
    en: "Use this as a risk check before buying. It is informational data, not investment advice.",
    bn: "কেনার আগে এটি ঝুঁকি যাচাই হিসেবে ব্যবহার করুন। এটি তথ্যমূলক ডেটা, বিনিয়োগ পরামর্শ নয়।",
  },
  "setup.clean": { en: "Clean read", bn: "পরিষ্কার রিড" },
  "setup.mixed": { en: "Mixed read", bn: "মিশ্র রিড" },
  "setup.risky": { en: "High-risk read", bn: "উচ্চ-ঝুঁকি রিড" },
  "catalyst.latest": { en: "Latest catalyst", bn: "সাম্প্রতিক কারণ" },
  "tech.aboveBoth": {
    en: "Above 50 & 200-day average",
    bn: "৫০ ও ২০০-দিনের গড়ের উপরে",
  },
  "tech.belowBoth": {
    en: "Below 50 & 200-day average",
    bn: "৫০ ও ২০০-দিনের গড়ের নিচে",
  },
  "tech.mixedMa": {
    en: "Mixed vs moving averages",
    bn: "মুভিং এভারেজের মিশ্র অবস্থান",
  },
  "tech.momentum": { en: "Momentum (RSI 14)", bn: "মোমেন্টাম (RSI 14)" },
  "tech.volVs20": { en: "Volume vs 20-day", bn: "২০-দিনের তুলনায় ভলিউম" },
  "tech.nearestSupport": { en: "Nearest support", bn: "নিকটতম সাপোর্ট" },
  "tech.nearestResistance": {
    en: "Nearest resistance",
    bn: "নিকটতম রেজিস্ট্যান্স",
  },
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
  "markets.searchPlaceholder": {
    en: "Search a code, e.g. GP → Enter",
    bn: "কোড লিখুন, যেমন GP → এন্টার",
  },
  "markets.lookingFor": {
    en: "What are you looking for?",
    bn: "আপনি কী খুঁজছেন?",
  },
  "markets.browseAll": {
    en: "Every board, grouped for power users.",
    bn: "পাওয়ার ইউজারের জন্য সব বোর্ড, গ্রুপ অনুযায়ী।",
  },
  "markets.focusBlurb": {
    en: "High-signal boards for today's DSE read.",
    bn: "আজকের DSE পড়ার জন্য গুরুত্বপূর্ণ বোর্ড।",
  },
  "markets.footer": {
    en: "Computed from end-of-day prices · descriptive screens, not recommendations.",
    bn: "দিনশেষের দাম থেকে গণনা · তথ্যমূলক স্ক্রিন, সুপারিশ নয়।",
  },
  viewMore: { en: "View more →", bn: "আরও দেখুন →" },
  "rowDetails.title": { en: "Stock brief", bn: "স্টক ব্রিফ" },
  "rowDetails.open": { en: "Open full stock page", bn: "পুরো স্টক পেজ খুলুন" },
  "rowDetails.why": { en: "Why it appears", bn: "কেন দেখাচ্ছে" },
  "rowDetails.summary": { en: "Quick read", bn: "দ্রুত সারাংশ" },
  "rowDetails.context": { en: "How to read this board", bn: "এই বোর্ড কীভাবে পড়বেন" },
  "rowDetails.checks": { en: "What to verify next", bn: "এরপর কী যাচাই করবেন" },
  "rowDetails.execution": { en: "Execution check", bn: "লেনদেনের ঝুঁকি চেক" },
  "rowDetails.liquidity": { en: "Liquidity", bn: "লিকুইডিটি" },
  "rowDetails.order": { en: "Order guide", bn: "অর্ডার গাইড" },
  "rowDetails.value": { en: "Board metric", bn: "বোর্ড মেট্রিক" },
  "rowDetails.price": { en: "Price", bn: "দাম" },
  "rowDetails.catalyst": { en: "Latest catalyst", bn: "সাম্প্রতিক কারণ" },
  "rowDetails.marketCap": { en: "Market cap", bn: "মার্কেট ক্যাপ" },
  "rowDetails.freeFloat": { en: "Free-float cap", bn: "ফ্রি-ফ্লোট ক্যাপ" },
  "rowDetails.turnover": { en: "Today turnover", bn: "আজকের টার্নওভার" },
  "rowDetails.orderHelp": {
    en: "Roughly 5% of ADTV. Bigger orders may need splitting so your own trade does not move the price.",
    bn: "ADTV-এর প্রায় ৫%। এর বেশি অর্ডার হলে ভাগ করে দেওয়া লাগতে পারে, যাতে আপনার অর্ডারেই দাম না নড়ে।",
  },
  "rowDetails.fullHint": {
    en: "Open the full page for chart, news, fundamentals, ownership, levels, and community context.",
    bn: "চার্ট, খবর, ফান্ডামেন্টাল, মালিকানা, লেভেল ও কমিউনিটি প্রসঙ্গের জন্য পুরো স্টক পেজ খুলুন।",
  },
  "rowDetails.ctaSub": {
    en: "Chart, news, fundamentals, ownership, and key levels in one view",
    bn: "চার্ট, খবর, ফান্ডামেন্টাল, মালিকানা ও গুরুত্বপূর্ণ লেভেল একসাথে",
  },
  "col.symbol": { en: "Symbol", bn: "টিকার" },
  "col.price": { en: "Price", bn: "দাম" },
  nothingHere: { en: "Nothing here right now.", bn: "এই মুহূর্তে কিছু নেই।" },
  "screen.descNote": {
    en: "Descriptive screen — not a recommendation.",
    bn: "তথ্যমূলক স্ক্রিন — সুপারিশ নয়।",
  },
  backToMarkets: { en: "← Markets", bn: "← মার্কেট" },
  backToPatterns: { en: "← Chart patterns", bn: "← চার্ট প্যাটার্ন" },
  "patterns.title": { en: "Chart Patterns", bn: "চার্ট প্যাটার্ন" },
  "patterns.intro": {
    en: "Classic technical shapes built from confirmed swing highs/lows. Tap a pattern to see what it means, what textbook technical analysis says usually happens next, and which DSE stocks are showing it right now.",
    bn: "নিশ্চিত সুইং হাই/লো থেকে তৈরি ক্লাসিক টেকনিক্যাল আকার। কোনো প্যাটার্নে ট্যাপ করে দেখুন এর মানে কী, প্রথাগত টেকনিক্যাল অ্যানালাইসিস অনুযায়ী সাধারণত এরপর কী হয়, আর এখন কোন DSE শেয়ার এটি দেখাচ্ছে।",
  },
  "patterns.showingCount": {
    en: "{n} DSE stocks showing this now",
    bn: "এখন {n}টি DSE শেয়ার এটি দেখাচ্ছে",
  },
  "patterns.showingNone": { en: "No DSE stocks showing this right now", bn: "এখন কোনো DSE শেয়ার এটি দেখাচ্ছে না" },
  "patterns.showingNow": { en: "Showing this now", bn: "এখন যা দেখাচ্ছে" },
  "patterns.unknown": { en: "Unknown pattern.", bn: "অজানা প্যাটার্ন।" },
  "explore.moverReversal": {
    en: "1-month moves often reverse. For a lasting trend, see “Strongest trend”.",
    bn: "১-মাসের মুভ প্রায়ই উল্টে যায়। টেকসই প্রবণতার জন্য “সবচেয়ে শক্তিশালী প্রবণতা” দেখুন।",
  },
  "explore.dotsNote": {
    en: "Dots = climbing over 3M·6M·12M (green = strong). All three green means the uptrend is broad, not just recent.",
    bn: "ডট = ৩M·৬M·১২M-এ উঠছে (সবুজ = শক্তিশালী)। তিনটিই সবুজ মানে প্রবণতা ব্যাপক, শুধু সাম্প্রতিক নয়।",
  },
  // Lens chips
  "lens.focus": { en: "Focus", bn: "ফোকাস" },
  "lens.all": { en: "All boards", bn: "সব বোর্ড" },
  "lens.momentum": { en: "Momentum", bn: "মোমেন্টাম" },
  "lens.value": { en: "Value", bn: "ভ্যালু" },
  "lens.smart": { en: "Smart money", bn: "স্মার্ট মানি" },
  "lens.dividend": { en: "Dividend", bn: "লভ্যাংশ" },
  "lens.steady": { en: "Steady", bn: "স্থির" },
  "lens.patterns": { en: "Chart patterns", bn: "চার্ট প্যাটার্ন" },
  "lens.momentum.blurb": {
    en: "Stocks moving and trending — for traders who want strength.",
    bn: "যেসব শেয়ার নড়ছে ও প্রবণতায় আছে — শক্তি খোঁজা ট্রেডারদের জন্য।",
  },
  "lens.value.blurb": {
    en: "Cheap, profitable, growing — for bargain hunters.",
    bn: "সস্তা, লাভজনক, বর্ধনশীল — দরদাম খোঁজাদের জন্য।",
  },
  "lens.smart.blurb": {
    en: "Institutional, foreign and volume-flow clues — history, not a signal to follow blindly.",
    bn: "প্রতিষ্ঠান, বিদেশি ও ভলিউম-ফ্লোর ইঙ্গিত — ইতিহাস, অন্ধভাবে অনুসরণের সংকেত নয়।",
  },
  "lens.dividend.blurb": {
    en: "Cash payers — for income seekers.",
    bn: "নগদ লভ্যাংশদাতা — আয়-সন্ধানীদের জন্য।",
  },
  "lens.steady.blurb": {
    en: "Low-swing, quality names — for a calmer ride.",
    bn: "কম ওঠানামা, মানসম্পন্ন — শান্ত যাত্রার জন্য।",
  },
  "lens.patterns.blurb": {
    en: "Classic chart shapes currently forming — textbook technical analysis, not proven on DSE.",
    bn: "এখন গঠিত হচ্ছে এমন ক্লাসিক চার্ট আকার — প্রথাগত টেকনিক্যাল অ্যানালাইসিস, DSE-তে প্রমাণিত নয়।",
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
  "mh.strength": { en: "Strength", bn: "শক্তি" },
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
  "mc.reducing": { en: "Insiders reducing", bn: "অভ্যন্তরীণরা কমাচ্ছেন" },
  "mc.highlyProfitable": { en: "Highly profitable", bn: "অত্যন্ত লাভজনক" },
  "mc.profitable": { en: "Profitable", bn: "লাভজনক" },
  "mc.verySteady": { en: "Very steady", bn: "খুব স্থির" },
  "mc.steady": { en: "Steady", bn: "স্থির" },
  "mc.outperforming": { en: "Outperforming", bn: "বাজারকে ছাড়িয়ে" },
  // Feed
  "feed.loginCta": {
    en: "Log in to post your call →",
    bn: "আপনার মতামত পোস্ট করতে লগ ইন করুন →",
  },
  "feed.empty": {
    en: "No posts yet — be the first. Automated market notes live in 🐂 Bulls.",
    bn: "এখনো কোনো পোস্ট নেই — প্রথম মতামত দিন। স্বয়ংক্রিয় মার্কেট নোট আছে 🐂 বুলস-এ।",
  },
  "feed.emptyWatched": {
    en: "Build your feed — follow official desks in 🐂 Bulls and tap ☆ Watch on companies. Their posts show up here.",
    bn: "আপনার ফিড সাজান — 🐂 বুলস-এ অফিসিয়াল ডেস্ক ফলো করুন এবং কোম্পানিতে ☆ Watch চাপুন। তাদের পোস্ট এখানে আসবে।",
  },
  "home.today": { en: "Today", bn: "আজ" },
  "home.discussion": { en: "Discussion", bn: "আলোচনা" },
  "home.latest": { en: "Latest", bn: "সর্বশেষ" },
  "home.watchlistFeed": { en: "From your watchlist", bn: "আপনার ওয়াচলিস্ট থেকে" },
  "home.earningsWeek": { en: "Earnings this week", bn: "এই সপ্তাহের আয় ঘোষণা" },
  "home.earningsWeekSub": {
    en: "Board meetings called to consider results",
    bn: "ফলাফল বিবেচনায় ডাকা বোর্ড সভা",
  },
  "home.earningsWeekNote": {
    en: "Announced dates — companies can reschedule.",
    bn: "ঘোষিত তারিখ — কোম্পানি সময় বদলাতে পারে।",
  },
  "home.myFeed": { en: "Your feed", bn: "আপনার ফিড" },
  "home.signedOutTitle": {
    en: "Your market, your feed",
    bn: "আপনার বাজার, আপনার ফিড",
  },
  "home.signedOutBody": {
    en: "Sign in to follow official desks and watch companies — their posts and alerts land right here, just the signals you care about.",
    bn: "সাইন ইন করুন — অফিসিয়াল ডেস্ক ফলো করুন ও কোম্পানি ওয়াচ করুন, তাদের পোস্ট ও অ্যালার্ট ঠিক এখানে আসবে, শুধু আপনার পছন্দের সংকেত।",
  },
  "home.signInCta": { en: "Sign in / Create account", bn: "সাইন ইন / অ্যাকাউন্ট খুলুন" },
  "home.browseBulls": {
    en: "Or browse everything in 🐂 Bulls →",
    bn: "অথবা সব দেখুন 🐂 বুলস-এ →",
  },
  "home.emptyTitle": { en: "This is your feed", bn: "এটি আপনার ফিড" },
  "home.emptyBody": {
    en: "It fills with posts from the official desks you follow and the companies you watch. Follow a few to get started.",
    bn: "আপনি যে অফিসিয়াল ডেস্ক ফলো করেন ও যে কোম্পানি ওয়াচ করেন, তাদের পোস্টে এটি ভরে ওঠে। শুরু করতে কয়েকটি ফলো করুন।",
  },
  "home.followDesks": { en: "Follow desks", bn: "ডেস্ক ফলো করুন" },
  "home.watchStocks": { en: "Watch stocks", bn: "শেয়ার ওয়াচ করুন" },
  "bulls.all": { en: "All", bn: "সব" },
  // Bulls feed
  "bulls.feedTitle": { en: "Bulls Feed", bn: "বুলস ফিড" },
  "bulls.feedDesc": {
    en: "Automated data notes across the market — levels, volume, ownership and more. Descriptive, not advice.",
    bn: "বাজার জুড়ে স্বয়ংক্রিয় ডেটা নোট — লেভেল, ভলিউম, মালিকানা ও আরও। তথ্যমূলক, পরামর্শ নয়।",
  },
  "bulls.empty": {
    en: "No notes yet — they appear as the market moves.",
    bn: "এখনো কোনো নোট নেই — বাজার নড়লে আসবে।",
  },
  "bulls.feedDescNote": {
    en: "Descriptive, not advice.",
    bn: "তথ্যমূলক, পরামর্শ নয়।",
  },
  // Composer
  "composer.placeholder": {
    en: "What's your call? Use $GP to tag a stock…",
    bn: "আপনার মতামত কী? স্টক ট্যাগ করতে $GP লিখুন…",
  },
  "composer.failed": { en: "Failed to post", bn: "পোস্ট করা যায়নি" },
  "composer.pending": {
    en: "Sent for review. It will appear after approval.",
    bn: "রিভিউতে পাঠানো হয়েছে। অনুমোদনের পর দেখা যাবে।",
  },
  "composer.tickerHint": {
    en: "Tip: type $ (or @) then a few letters to tag a ticker.",
    bn: "টিপস: টিকার ট্যাগ করতে $ (বা @) লিখে কয়েকটি অক্ষর টাইপ করুন।",
  },
  "composer.bull": { en: "▲ Bull", bn: "▲ তেজি" },
  "composer.bear": { en: "▼ Bear", bn: "▼ মন্দা" },
  "common.post": { en: "Post", bn: "পোস্ট" },
  "common.reply": { en: "Reply", bn: "রিপ্লাই" },
  "common.loading": { en: "Loading…", bn: "লোড হচ্ছে…" },
  "common.close": { en: "Close", bn: "বন্ধ" },
  // Post card
  "post.agree": { en: "Agree with this take", bn: "এই মতের সাথে একমত" },
  "post.disagree": { en: "Disagree with this take", bn: "এই মতের সাথে দ্বিমত" },
  "post.loginReact": {
    en: "Log in to react",
    bn: "প্রতিক্রিয়া জানাতে লগ ইন করুন",
  },
  "post.replyPlaceholder": { en: "Reply…", bn: "রিপ্লাই…" },
  "post.noReplies": { en: "No replies yet.", bn: "এখনো কোনো রিপ্লাই নেই।" },
  "post.delete": { en: "Delete", bn: "মুছুন" },
  "post.deleteAdmin": { en: "Delete (admin)", bn: "মুছুন (অ্যাডমিন)" },
  "post.confirmDelete": {
    en: "Delete this post? It will be removed from the feed.",
    bn: "এই পোস্টটি মুছবেন? এটি ফিড থেকে সরিয়ে ফেলা হবে।",
  },
  "post.dataNote": { en: "Auto · facts only", bn: "স্বয়ংক্রিয় · শুধু তথ্য" },
  "post.officialDesk": {
    en: "Official desk · facts only",
    bn: "অফিসিয়াল ডেস্ক · শুধু তথ্য",
  },
  "desk.official": { en: "Official Bulls of Dhaka Desk", bn: "অফিসিয়াল বুলস অব ঢাকা ডেস্ক" },
  "desk.posts": { en: "posts", bn: "পোস্ট" },
  "desk.followers": { en: "followers", bn: "ফলোয়ার" },
  "desk.follow": { en: "Follow", bn: "ফলো" },
  "desk.following": { en: "Following", bn: "ফলো করছেন" },
  "desk.joined": { en: "Joined", bn: "যোগ দিয়েছে" },
  "desk.postsHeading": { en: "Posts", bn: "পোস্ট" },
  "desk.noPosts": { en: "No posts yet.", bn: "এখনো কোনো পোস্ট নেই।" },
  "desk.notFound": { en: "Desk not found.", bn: "ডেস্ক পাওয়া যায়নি।" },
  "userProfile.notFound": { en: "Member not found.", bn: "সদস্য পাওয়া যায়নি।" },
  "userProfile.portfolioHeading": { en: "Portfolio (public)", bn: "পোর্টফোলিও (প্রকাশ্য)" },
  "post.agreeBtn": { en: "Agree", bn: "একমত" },
  "post.disagreeBtn": { en: "Disagree", bn: "দ্বিমত" },
  "post.loginReply": {
    en: "Log in to reply →",
    bn: "রিপ্লাই করতে লগ ইন করুন →",
  },
  "post.reply": { en: "reply", bn: "রিপ্লাই" },
  // A holding's total gain since purchase — the one % that needs a label to avoid being
  // misread as today's move. See the Pct component.
  "pct.sinceBuy": { en: "since buy", bn: "কেনার পর থেকে" },
  "post.replies": { en: "replies", bn: "রিপ্লাই" },
  // Today's standouts
  "standouts.title": { en: "Today's standouts", bn: "আজকের আলোচিত" },
  "standouts.subtitle": {
    en: "The day's biggest signals at a glance — descriptive, not advice.",
    bn: "এক নজরে দিনের সবচেয়ে বড় সংকেত — তথ্যমূলক, পরামর্শ নয়।",
  },
  "standouts.exploreAll": {
    en: "Explore all screens →",
    bn: "সব স্ক্রিন দেখুন →",
  },
  "standouts.topMover": { en: "Top mover", bn: "টপ মুভার" },
  "standouts.strongestTrend": {
    en: "Strongest trend",
    bn: "সবচেয়ে শক্তিশালী প্রবণতা",
  },
  "standouts.quietAccum": { en: "Quiet accumulation", bn: "নীরব সঞ্চয়" },
  "standouts.beatingMarket": {
    en: "Beating the market",
    bn: "বাজারকে ছাড়িয়ে",
  },
  "standouts.foreignBuying": { en: "Foreign buying", bn: "বিদেশি ক্রয়" },
  "standouts.unusualVolume": { en: "Unusual volume", bn: "অস্বাভাবিক ভলিউম" },
  // InfoTip + LearnSheet
  "infoTip.learn": {
    en: "Learn how to use it →",
    bn: "কীভাবে ব্যবহার করবেন শিখুন →",
  },
  "infoTip.aria": { en: "What is this?", bn: "এটি কী?" },
  "learn.what": { en: "What it is", bn: "এটি কী" },
  "learn.use": {
    en: "How traders use it",
    bn: "ট্রেডাররা যেভাবে ব্যবহার করেন",
  },
  "learn.watch": { en: "Watch out for", bn: "যা খেয়াল রাখবেন" },
  "learn.example": { en: "Example", bn: "উদাহরণ" },
  "learn.footer": {
    en: "Educational only — not a recommendation to buy or sell.",
    bn: "শুধু শিক্ষামূলক — কেনা বা বেচার সুপারিশ নয়।",
  },
  // Fundamentals panel row labels
  "f.marketCap": { en: "Market cap", bn: "বাজার মূলধন" },
  "f.pe": { en: "P/E", bn: "পি/ই" },
  "f.peSector": { en: "P/E vs sector", bn: "P/E খাতের তুলনায়" },
  "f.pb": { en: "P/B", bn: "পি/বি" },
  "f.divYield": { en: "Dividend yield", bn: "লভ্যাংশ ইল্ড" },
  "f.epsAnnual": { en: "EPS (annual)", bn: "ইপিএস (বার্ষিক)" },
  "f.epsGrowthYoY": { en: "EPS growth (YoY)", bn: "ইপিএস বৃদ্ধি (YoY)" },
  "f.navShare": { en: "NAV / share", bn: "NAV / শেয়ার" },
  "f.freeFloatCap": { en: "Free-float cap", bn: "ফ্রি-ফ্লোট ক্যাপ" },
  "f.sharesOut": { en: "Shares outstanding", bn: "মোট শেয়ার" },
  "f.faceValue": { en: "Face value", bn: "ফেস ভ্যালু" },
  "f.sector": { en: "Sector", bn: "খাত" },
  "f.creditRating": { en: "Credit rating", bn: "ক্রেডিট রেটিং" },
  // News panel
  "news.empty": {
    en: "No news yet for this stock.",
    bn: "এই শেয়ারের জন্য এখনো খবর নেই।",
  },
  "news.strength": { en: "strength", bn: "শক্তি" },
  "news.footer": {
    en: "Exchange disclosures. Descriptive, not advice.",
    bn: "এক্সচেঞ্জ প্রকাশ। তথ্যমূলক, পরামর্শ নয়।",
  },
  // decoded news — period labels
  "news.period.Q1": { en: "First quarter", bn: "প্রথম প্রান্তিক" },
  "news.period.H1": { en: "Half-year", bn: "অর্ধবার্ষিক" },
  "news.period.Q3": { en: "Third quarter", bn: "তৃতীয় প্রান্তিক" },
  "news.period.annual": { en: "Annual", bn: "বার্ষিক" },
  // earnings
  "news.eps": { en: "EPS this period", bn: "এই প্রান্তিকে ইপিএস" },
  "news.epsVsPrior": { en: "a year ago {prior}", bn: "গত বছর একই সময়ে {prior}" },
  "news.nav": { en: "NAV per share", bn: "প্রতি শেয়ারে এনএভি" },
  "news.navHint": { en: "book value backing", bn: "বইমূল্যের সমর্থন" },
  "news.trend.loss_widened": { en: "Loss widened", bn: "লোকসান বেড়েছে" },
  "news.trend.loss_narrowed": { en: "Loss narrowed", bn: "লোকসান কমেছে" },
  "news.trend.up": { en: "Profit up", bn: "মুনাফা বেড়েছে" },
  "news.trend.down": { en: "Profit down", bn: "মুনাফা কমেছে" },
  "news.trend.to_loss": { en: "Turned to loss", bn: "মুনাফা থেকে লোকসান" },
  "news.trend.to_profit": { en: "Returned to profit", bn: "লোকসান থেকে মুনাফা" },
  "news.explain.earnings": {
    en: "EPS is profit per share for the period. Compare it with the same period a year ago to read the direction; a negative figure means a loss.",
    bn: "ইপিএস হলো প্রান্তিকে প্রতি শেয়ারে মুনাফা। গত বছরের একই সময়ের সাথে তুলনা করলে গতিপথ বোঝা যায়; ঋণাত্মক মানে লোকসান।",
  },
  // dividend
  "news.div.cash": { en: "{pct}% cash dividend", bn: "{pct}% নগদ লভ্যাংশ" },
  "news.div.perShare": { en: "= ৳{amt} per share", bn: "= প্রতি শেয়ারে ৳{amt}" },
  "news.div.stock": { en: "{pct}% stock dividend (bonus shares)", bn: "{pct}% স্টক লভ্যাংশ (বোনাস শেয়ার)" },
  "news.div.none": { en: "No dividend declared", bn: "কোনো লভ্যাংশ ঘোষণা করা হয়নি" },
  "news.div.forYear": { en: "for the year ended {year}", bn: "{year} সালের বছরের জন্য" },
  "news.div.example": {
    en: "Hold 100 shares on the record date → ৳{amt} cash (before tax).",
    bn: "রেকর্ড ডেটে ১০০ শেয়ার থাকলে → ৳{amt} নগদ (করের আগে)।",
  },
  "news.div.priceAdj": {
    en: "On the ex-date the price drops about ৳{amt} automatically — the dividend leaving the price, not a market fall.",
    bn: "এক্স-ডেটে দাম প্রায় ৳{amt} স্বয়ংক্রিয়ভাবে কমে — এটি লভ্যাংশ দাম থেকে বেরিয়ে যাওয়া, বাজারে পতন নয়।",
  },
  "news.div.faceNote": { en: "on ৳{face} face value", bn: "৳{face} অভিহিত মূল্যে" },
  // dates
  "news.recordDate": { en: "Record date", bn: "রেকর্ড ডেট" },
  "news.spotMarket": { en: "Spot market", bn: "স্পট মার্কেট" },
  "news.agm": { en: "AGM", bn: "এজিএম" },
  "news.meetingDate": { en: "Meeting", bn: "সভা" },
  "news.explain.dates": {
    en: "You must hold the share on the record date to be eligible. In the run-up it trades in the spot market (immediate settlement), and trading is suspended on the record date itself.",
    bn: "যোগ্য হতে রেকর্ড ডেটে শেয়ার ধরে রাখতে হবে। এর আগে এটি স্পট মার্কেটে (তাৎক্ষণিক নিষ্পত্তি) লেনদেন হয়, এবং রেকর্ড ডেটে লেনদেন স্থগিত থাকে।",
  },
  // board meeting
  "news.board.title": { en: "Board meets {date} to consider {what}", bn: "{date} বোর্ড সভা — বিবেচ্য: {what}" },
  "news.board.financials": { en: "{period} results", bn: "{period} ফলাফল" },
  "news.board.dividend": { en: "a dividend", bn: "লভ্যাংশ" },
  "news.board.and": { en: " and ", bn: " ও " },
  "news.explain.board": {
    en: "A heads-up. Results — and any dividend — usually follow shortly after this meeting.",
    bn: "একটি আগাম বার্তা। ফলাফল — এবং কোনো লভ্যাংশ — সাধারণত এই সভার পরপরই আসে।",
  },
  // rating
  "news.rating.line": { en: "{lt} long-term · {st} short-term", bn: "{lt} দীর্ঘমেয়াদি · {st} স্বল্পমেয়াদি" },
  "news.rating.outlook": { en: "{outlook} outlook", bn: "{outlook} আউটলুক" },
  "news.rating.upgrade": { en: "Upgrade", bn: "উন্নীত" },
  "news.rating.downgrade": { en: "Downgrade", bn: "অবনমিত" },
  "news.explain.rating": {
    en: "A credit rating agency's view of the company's ability to repay its debts — higher grades mean lower default risk.",
    bn: "কোম্পানির ঋণ পরিশোধের সক্ষমতা নিয়ে রেটিং সংস্থার মূল্যায়ন — উচ্চ গ্রেড মানে কম ঝুঁকি।",
  },
  "news.whatItMeans": { en: "What it means", bn: "এর অর্থ" },
  "news.filter.all": { en: "All", bn: "সব" },
  "news.filter.earnings": { en: "Earnings", bn: "আয়" },
  "news.filter.dividend": { en: "Dividends", bn: "লভ্যাংশ" },
  "news.filter.meeting": { en: "Meetings", bn: "সভা" },
  "news.filter.rating": { en: "Ratings", bn: "রেটিং" },
  "news.upcoming": { en: "Upcoming", bn: "আসন্ন" },
  "news.digest.title": { en: "Last 12 months", bn: "গত ১২ মাস" },
  "news.digest.dividend": { en: "Latest dividend", bn: "সর্বশেষ লভ্যাংশ" },
  "news.digest.eps": { en: "Latest EPS", bn: "সর্বশেষ ইপিএস" },
  "news.digest.cash": { en: "{pct}% cash", bn: "{pct}% নগদ" },
  "news.digest.bonus": { en: " + {pct}% bonus", bn: " + {pct}% বোনাস" },
  "news.digest.streak": { en: "Profitable quarters", bn: "লাভজনক প্রান্তিক" },
  "news.digest.streakVal": { en: "{n} of {m}", bn: "{m}-এর {n}টি" },
  "news.digest.rating": { en: "Credit rating", bn: "ক্রেডিট রেটিং" },
  "news.digest.rated": { en: "rated {date}", bn: "রেটেড {date}" },
  "cat.dividend": { en: "Dividend", bn: "লভ্যাংশ" },
  "cat.earnings": { en: "Earnings", bn: "আয়" },
  "cat.rating": { en: "Rating", bn: "রেটিং" },
  "cat.insider": { en: "Insider dealing", bn: "অভ্যন্তরীণ লেনদেন" },
  "cat.board_meeting": { en: "Board meeting", bn: "বোর্ড সভা" },
  "cat.corporate_action": { en: "Corporate action", bn: "কর্পোরেট অ্যাকশন" },
  "cat.halt": { en: "Halt", bn: "স্থগিত" },
  "cat.psi": { en: "Price-sensitive", bn: "মূল্য-সংবেদনশীল" },
  "cat.other": { en: "Other", bn: "অন্যান্য" },
  // Watch today (trending activity)
  "watch.title": { en: "Active today", bn: "আজকের সক্রিয়" },
  "watch.subtitle": {
    en: "Stocks unusually busy versus their own normal trading. ADTV and Order guide help you judge entry/exit risk.",
    bn: "নিজের স্বাভাবিক লেনদেনের তুলনায় অস্বাভাবিক ব্যস্ত শেয়ার। ADTV ও অর্ডার গাইড ঢোকা/বের হওয়ার ঝুঁকি বুঝতে সাহায্য করে।",
  },
  "watch.heating": { en: "Heating up", bn: "সরগরম" },
  "watch.empty": { en: "No standout activity yet today.", bn: "আজ এখনো উল্লেখযোগ্য সক্রিয়তা নেই।" },
  "watch.footer": {
    en: "Ranked from latest completed trading data by volume + turnover anomaly. Liquid names only. Past activity, not a prediction.",
    bn: "সর্বশেষ সম্পন্ন ট্রেডিং ডেটা থেকে ভলিউম + টার্নওভার অস্বাভাবিকতা দিয়ে র‍্যাঙ্ক। শুধু তারল্যপূর্ণ নাম। অতীত সক্রিয়তা, ভবিষ্যদ্বাণী নয়।",
  },
  "watch.r.volume": { en: "{mult}× normal volume", bn: "{mult}× স্বাভাবিক ভলিউম" },
  "watch.r.turnover": { en: "৳{cr}cr turnover", bn: "৳{cr}কোটি টার্নওভার" },
  "watch.r.turnoverMult": { en: "৳{cr}cr ({mult}× usual)", bn: "৳{cr}কোটি ({mult}× স্বাভাবিকের)" },
  "watch.r.near_high": { en: "near 52-week high", bn: "৫২-সপ্তাহের সর্বোচ্চের কাছে" },
  "watch.r.near_low": { en: "near 52-week low", bn: "৫২-সপ্তাহের সর্বনিম্নের কাছে" },
  "watch.r.move": { en: "{pct}% move", bn: "{pct}% নড়াচড়া" },
  "watch.r.limit_up": { en: "locked limit-up", bn: "সর্বোচ্চ সীমায় আটকে" },
  "watch.r.limit_down": { en: "locked limit-down", bn: "সর্বনিম্ন সীমায় আটকে" },
  // Watchlist + Profile
  "common.login": { en: "Log in", bn: "লগ ইন" },
  "common.cancel": { en: "Cancel", bn: "বাতিল" },
  "wl.toBuild": {
    en: "to build your watchlist.",
    bn: "আপনার ওয়াচলিস্ট তৈরি করতে।",
  },
  "wl.empty": {
    en: "Your watchlist is empty. Tap ☆ on any symbol.",
    bn: "আপনার ওয়াচলিস্ট খালি। যেকোনো শেয়ারে ☆ ট্যাপ করুন।",
  },
  "profile.logout": { en: "Log out", bn: "লগ আউট" },
  "profile.watchlist": { en: "☆ Your watchlist", bn: "☆ আপনার ওয়াচলিস্ট" },
  "profile.publicPortfolio": { en: "Public portfolio", bn: "প্রকাশ্য পোর্টফোলিও" },
  "profile.publicPortfolioHint": {
    en: "Off by default. If you turn this on, anyone can see your holdings and growth chart on your public profile.",
    bn: "ডিফল্টে বন্ধ। চালু করলে যে কেউ আপনার প্রোফাইলে হোল্ডিং ও প্রবৃদ্ধি চার্ট দেখতে পাবে।",
  },
  "profile.viewPublicProfile": { en: "View your public profile", bn: "আপনার প্রকাশ্য প্রোফাইল দেখুন" },
  "profile.error": { en: "Something went wrong", bn: "কিছু ভুল হয়েছে" },
  "profile.welcomeBack": { en: "Welcome back", bn: "আবার স্বাগতম" },
  "profile.join": {
    en: "Join Bulls of Dhaka",
    bn: "Bulls of Dhaka-তে যোগ দিন",
  },
  "profile.handle": {
    en: "username — e.g. rahim_dhaka",
    bn: "ইউজারনেম — যেমন rahim_dhaka",
  },
  "profile.handleHint": {
    en: "Your public @name. Letters, numbers and _ only — no spaces.",
    bn: "আপনার পাবলিক @নাম। শুধু অক্ষর, সংখ্যা ও _ — কোনো স্পেস নয়।",
  },
  "profile.name": { en: "full name", bn: "পুরো নাম" },
  "profile.emailOrPhone": { en: "email or phone number", bn: "ইমেইল বা ফোন নম্বর" },
  "profile.loginId": {
    en: "email, phone, or username",
    bn: "ইমেইল, ফোন বা ইউজারনেম",
  },
  "profile.autoHandleHint": {
    en: "Your username is created automatically from your name.",
    bn: "আপনার নাম থেকে ইউজারনেম স্বয়ংক্রিয়ভাবে তৈরি হবে।",
  },
  "profile.account": { en: "Account & verification", bn: "অ্যাকাউন্ট ও যাচাই" },
  "profile.emailLabel": { en: "Email", bn: "ইমেইল" },
  "profile.phoneLabel": { en: "Phone", bn: "ফোন" },
  "profile.verified": { en: "✓ Verified", bn: "✓ যাচাইকৃত" },
  "profile.unverified": { en: "Unverified", bn: "যাচাই করা হয়নি" },
  "profile.verifyBtn": { en: "Verify", bn: "যাচাই করুন" },
  "profile.verifySent": {
    en: "Verification link sent — check your email.",
    bn: "যাচাই লিংক পাঠানো হয়েছে — আপনার ইমেইল দেখুন।",
  },
  "profile.notAdded": { en: "not added", bn: "যোগ করা হয়নি" },
  "profile.add": { en: "Add", bn: "যোগ করুন" },
  "profile.change": { en: "Change", bn: "পরিবর্তন" },
  "profile.save": { en: "Save", bn: "সেভ" },
  "profile.phoneVerifySoon": {
    en: "Phone verification coming soon",
    bn: "ফোন যাচাই শীঘ্রই আসছে",
  },
  "profile.badPhone": {
    en: "Enter a valid phone number (with country code if outside Bangladesh)",
    bn: "সঠিক ফোন নম্বর দিন (বাংলাদেশের বাইরে হলে কান্ট্রি কোডসহ)",
  },
  "profile.password": {
    en: "password (min 8 chars)",
    bn: "পাসওয়ার্ড (কমপক্ষে ৮ অক্ষর)",
  },
  "profile.createAccount": { en: "Create account", bn: "অ্যাকাউন্ট তৈরি করুন" },
  "profile.toRegister": {
    en: "New here? Create an account",
    bn: "নতুন? অ্যাকাউন্ট তৈরি করুন",
  },
  "profile.toLogin": {
    en: "Already have an account? Log in",
    bn: "অ্যাকাউন্ট আছে? লগ ইন করুন",
  },
  "profile.email": { en: "email", bn: "ইমেইল" },
  "profile.forgot": { en: "Forgot password?", bn: "পাসওয়ার্ড ভুলে গেছেন?" },
  "profile.contact": {
    en: "Questions? Contact us at",
    bn: "প্রশ্ন আছে? যোগাযোগ করুন",
  },
  "forgot.title": { en: "Reset your password", bn: "পাসওয়ার্ড রিসেট করুন" },
  "forgot.intro": {
    en: "Enter your email and we'll send a reset link.",
    bn: "আপনার ইমেইল দিন, আমরা একটি রিসেট লিংক পাঠাবো।",
  },
  "forgot.send": { en: "Send reset link", bn: "রিসেট লিংক পাঠান" },
  "forgot.sent": {
    en: "If that email is registered, a reset link is on its way — check your inbox.",
    bn: "ইমেইলটি নিবন্ধিত থাকলে একটি রিসেট লিংক পাঠানো হয়েছে — ইনবক্স দেখুন।",
  },
  "reset.title": { en: "Set a new password", bn: "নতুন পাসওয়ার্ড দিন" },
  "reset.newPassword": {
    en: "new password (min 8 chars)",
    bn: "নতুন পাসওয়ার্ড (কমপক্ষে ৮ অক্ষর)",
  },
  "reset.submit": { en: "Update password", bn: "পাসওয়ার্ড আপডেট করুন" },
  "reset.invalid": {
    en: "This reset link is invalid or has expired. Request a new one.",
    bn: "এই রিসেট লিংক অবৈধ বা মেয়াদোত্তীর্ণ। নতুন একটি চান।",
  },
  "verify.verifying": {
    en: "Verifying your email…",
    bn: "আপনার ইমেইল যাচাই করা হচ্ছে…",
  },
  "verify.ok": { en: "Email verified ✓", bn: "ইমেইল যাচাই হয়েছে ✓" },
  "verify.fail": {
    en: "This link is invalid or has expired.",
    bn: "এই লিংক অবৈধ বা মেয়াদোত্তীর্ণ।",
  },
  "common.backHome": { en: "Back to home", bn: "হোমে ফিরুন" },
  // Today's Watch / session brief
  "session.pre_open": { en: "Morning Brief", bn: "সকালের ব্রিফ" },
  "session.open": { en: "Midday Pulse", bn: "দুপুরের পালস" },
  "session.post_close": { en: "Evening Wrap", bn: "সন্ধ্যার সারসংক্ষেপ" },
  "session.weekend": { en: "Weekend Review", bn: "সাপ্তাহিক পর্যালোচনা" },
  "session.default": { en: "Today's Watch", bn: "আজকের নজর" },
  "watch.flat": { en: "flat", bn: "অপরিবর্তিত" },
  "watch.aiFooter": {
    en: "AI-generated from today's moves + chatter. Not financial advice.",
    bn: "আজকের মুভ ও আলোচনা থেকে AI-নির্মিত। আর্থিক পরামর্শ নয়।",
  },
};

interface I18n {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: string) => string;
}
const Ctx = createContext<I18n>({
  lang: _lang,
  setLang: () => {},
  t: (k) => k,
});

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(_lang);
  // Sync the non-React mirror SYNCHRONOUSLY at set time. The toggle remounts <main key={lang}>,
  // and child fetch effects (which read currentLang() via api.ts) run BEFORE the parent's effect
  // below — so updating _lang only in that effect made refetches use the PREVIOUS locale (the
  // "reverse language" bug). Setting it here, before the re-render, fixes the ordering.
  const setLang = (l: Lang) => {
    _lang = l;
    setLangState(l);
  };
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
  return <Ctx.Provider value={{ lang, setLang, t }}>{children}</Ctx.Provider>;
}

export const useLang = () => useContext(Ctx);
