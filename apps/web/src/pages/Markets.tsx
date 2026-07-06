import { useEffect, useState } from "react";
import { CompanyLogo } from "../components/CompanyLogo";
import { EarningsWeek } from "../components/EarningsWeek";
import { useSeo } from "../components/Seo";
import { EvidenceNote } from "../components/EvidenceChip";
import { Link } from "../lib/nav";
import {
  api,
  type MomHorizons,
  type Screen,
  type ScreenItem,
  type ScreensResponse,
} from "../lib/api";
import { Spinner, taka } from "../components/ui";
import { FreshnessTag } from "../components/FreshnessTag";
import { InfoTip } from "../components/InfoTip";
import { MarketPulse } from "../components/MarketPulse";
import { Sparkline } from "../components/Sparkline";
import { SectorHeat } from "../components/SectorHeat";
import { WatchToday } from "../components/WatchToday";
import { type Lang, useLang } from "../lib/i18n";
import { SCREEN_BN, SCREEN_LESSON } from "../lib/lessons";
import { PATTERN_ORDER, PATTERN_STATUS_LABEL } from "../lib/patterns";

// Plain-language explanation per screen, with a worked example — descriptive, never advice.
export const SCREEN_HELP: Record<string, string> = {
  top_gainers:
    "Biggest price moves up over the chosen period. e.g. +7.2% means the price is 7.2% higher than where it started.",
  top_losers:
    "Biggest price moves down over the chosen period. e.g. -7.2% means the price is 7.2% lower than where it started.",
  near_support:
    "Price sitting just above a support level — a floor buyers have defended before. 'Near' = within 3% above it. e.g. $GP 2% above ৳280 support.",
  near_resistance:
    "Price approaching a resistance level — a ceiling sellers have defended before. 'Near' = within 3% below it.",
  oversold:
    "RSI rates recent momentum from 0–100. Below 30 is historically an 'oversold' zone. e.g. RSI 25. A fact about momentum, not a buy signal.",
  overbought:
    "RSI rates recent momentum from 0–100. Above 70 is historically an 'overbought' zone. e.g. RSI 78. A fact about momentum, not a sell signal.",
  accumulation:
    "Chaikin Money Flow (CMF) gauges buying vs selling pressure over 20 days, on a -1 to +1 scale. Positive = money flowing in. e.g. +0.30 = strong inflow.",
  distribution:
    "Chaikin Money Flow (CMF) below 0 means money is flowing out — net selling pressure over 20 days. e.g. -0.30 = strong outflow.",
  unusual_volume:
    "How active a stock is vs its normal pace — a 1-day spike (1D) or sustained over a week/month (5D/1M). Tagged by today's direction: heavy volume while rising = buying, while falling = selling. e.g. 4.6x = 4.6 times its usual volume.",
  uptrend:
    "Trading above its 200-day average price — a common longer-term uptrend marker. The % shows how far above the average it is.",
  near_52w_high: "Within 5% of its highest price over the past 52 weeks (one year).",
  near_52w_low: "Within 5% of its lowest price over the past 52 weeks (one year).",
  dividend_yield:
    "Last year's cash dividend as a % of today's price. e.g. ৳1 cash on a ৳20 price = 5%. Bonus (stock) dividends aren't counted, and price-collapse 'traps' above 15% are hidden.",
  value_vs_sector:
    "P/E compared with the sector's median. Below 1.0× = cheaper than typical peers. e.g. 0.7× means a 30% lower P/E than the sector median.",
  eps_growth: "Earnings per share vs the prior year. e.g. +20% YoY = earnings grew 20%.",
  most_watched: "The names most people have added to their watchlist.",
  most_discussed: "The names with the most community posts over the last 2 days.",
  attention_rising:
    "Discussion running well above this symbol's own usual pace. e.g. 3× usual = three times its normal daily chatter.",
  quiet_accumulation:
    "Money is flowing in (positive Chaikin Money Flow) AND volume is confirming (On-Balance Volume trending up — volume leading price) while the price is still flat, within ~10% of its 50-day average. This 'buying into a quiet base' is the classic accumulation setup smart money looks for before a move. The flat price line next to a strong-inflow tag is the tell. A divergence, not a promise — bases can also just stay flat. Not advice.",
  foreign_buying:
    "How foreign investors increased their ownership since the prior disclosure. pp = percentage points (+5 pp ≈ they went from owning 10% to 15%). The line is the share price over that window; the dots are the stake at each disclosure (hover for figures). The 'since' date is the comparison point — disclosures come a few times a year, not daily. History, not a forecast.",
  institutional_buying:
    "How local institutions (mutual funds, asset managers) increased their ownership since the prior disclosure. See 'Institutional Selling' for the reverse — the same category can move both ways at once for different holders. pp = percentage points (+5 pp ≈ stake up 5 of the company's points). The line is the share price over that window; the dots are the stake at each disclosure. History, not a forecast.",
  institutional_selling:
    "How local institutions (mutual funds, asset managers) reduced their ownership since the prior disclosure. A different, separately-disclosed group from sponsors/directors below — funds trim for many routine reasons (rebalancing, redemptions), not just a loss of conviction. pp = percentage points. The line is the share price over that window; the dots are the stake at each disclosure. History, not a forecast.",
  sponsor_selling:
    "Sponsors/directors — the company's own insiders — reduced their stake since the prior disclosure. pp = percentage points of the company they let go. Insiders selling their own company is a disclosed fact worth reading into (why? to whom?), and a streak across disclosures matters more than one print. Not a sell signal by itself.",
  most_active:
    "Most heavily traded by money value today (price × volume), shown in crore (1 Cr = ৳10 million). The classic 'top turnover' board — where the day's action is, including the cheap, busy names.",
  beating_market:
    "Stocks rising more than the whole market (the DSEX index) over the past month. 'Relative strength' — going up while, or faster than, the market is the institutional tell for genuine strength. The value is how many % it beat the index by.",
  momentum_12_1:
    "12-month price trend, skipping the most recent month (which tends to reverse), then divided by volatility so a steady climb ranks above a wild one. e.g. +80% over the year. The quant 'momentum' factor — descriptive history, not a forecast.",
  quality_roe:
    "Return on equity = profit ÷ shareholder capital (EPS ÷ NAV per share). Higher = more profit per taka of book value. e.g. 25% ≈ ৳25 earned a year per ৳100 of net worth. A quality marker, not a buy signal.",
  low_volatility:
    "Annualised size of daily price swings over the past year. Lower = steadier. e.g. 15% is calm, 60% is wild. Steadier doesn't mean higher returns — just a smoother ride.",
};
// One board per pattern type (chart_pattern_ascending_triangle, etc.) — same explanatory text for
// all 7 since the "how to read this" logic is identical regardless of which specific shape it is.
for (const type of PATTERN_ORDER) {
  SCREEN_HELP[`chart_pattern_${type}`] =
    "Built from confirmed swing highs/lows. This is textbook technical analysis — not proven to predict DSE moves (our own study found the related momentum factor actually hurt returns here). Descriptive geometry, never a signal. Tap the board title for what this pattern means and what 'usually happens' does and doesn't tell you.";
}

// Bangla tooltip text — clear, simple retail phrasing (reviewed, not literal MT). Examples kept.
const SCREEN_HELP_BN: Record<string, string> = {
  top_gainers: "নির্বাচিত সময়ে দাম সবচেয়ে বেশি বেড়েছে। যেমন +৭.২% মানে দাম শুরুর চেয়ে ৭.২% বেশি।",
  top_losers: "নির্বাচিত সময়ে দাম সবচেয়ে বেশি কমেছে। যেমন -৭.২% মানে দাম শুরুর চেয়ে ৭.২% কম।",
  near_support:
    "দাম একটি সাপোর্ট লেভেলের ঠিক উপরে — যে তলা ক্রেতারা আগে রক্ষা করেছে। 'কাছে' = এর ৩% উপরে। যেমন $GP ৳২৮০ সাপোর্টের ২% উপরে।",
  near_resistance:
    "দাম একটি রেজিস্ট্যান্স লেভেলের কাছে — যে ছাদ বিক্রেতারা আগে রক্ষা করেছে। 'কাছে' = এর ৩% নিচে।",
  oversold:
    "RSI সাম্প্রতিক মোমেন্টাম ০–১০০-তে মাপে। ৩০-এর নিচে ঐতিহাসিকভাবে 'অতিরিক্ত বিক্রি' অঞ্চল। যেমন RSI ২৫। এটি মোমেন্টামের তথ্য, কেনার সংকেত নয়।",
  overbought:
    "RSI সাম্প্রতিক মোমেন্টাম ০–১০০-তে মাপে। ৭০-এর উপরে ঐতিহাসিকভাবে 'অতিরিক্ত কেনা' অঞ্চল। যেমন RSI ৭৮। এটি মোমেন্টামের তথ্য, বেচার সংকেত নয়।",
  accumulation:
    "Chaikin Money Flow (CMF) ২০ দিনে ক্রয় বনাম বিক্রয়চাপ মাপে, -১ থেকে +১ স্কেলে। ধনাত্মক = অর্থ ঢুকছে। যেমন +০.৩০ = জোরালো প্রবাহ।",
  distribution:
    "CMF ০-এর নিচে মানে অর্থ বেরোচ্ছে — ২০ দিনে নিট বিক্রয়চাপ। যেমন -০.৩০ = জোরালো বহিঃপ্রবাহ।",
  unusual_volume:
    "স্বাভাবিকের তুলনায় কতটা সক্রিয় — ১ দিনের স্পাইক (1D) বা সপ্তাহ/মাসজুড়ে (5D/1M)। আজকের দিক অনুযায়ী ট্যাগ: বাড়ার সময় ভারী ভলিউম = ক্রয়, পড়ার সময় = বিক্রয়। যেমন ৪.৬x = স্বাভাবিকের ৪.৬ গুণ।",
  uptrend:
    "২০০-দিনের গড় দামের উপরে লেনদেন — দীর্ঘমেয়াদি ঊর্ধ্বমুখী প্রবণতার সাধারণ চিহ্ন। % দেখায় গড়ের কতটা উপরে।",
  near_52w_high: "গত ৫২ সপ্তাহের (এক বছর) সর্বোচ্চ দামের ৫% মধ্যে।",
  near_52w_low: "গত ৫২ সপ্তাহের (এক বছর) সর্বনিম্ন দামের ৫% মধ্যে।",
  dividend_yield:
    "আজকের দামের শতাংশ হিসেবে গত বছরের নগদ লভ্যাংশ। যেমন ৳২০ দামে ৳১ নগদ = ৫%। বোনাস (শেয়ার) লভ্যাংশ গণনা হয় না, এবং দাম-ধসের ১৫%+ 'ট্র্যাপ' লুকানো থাকে।",
  value_vs_sector:
    "খাতের মধ্যমার সাথে P/E তুলনা। ১.০×-এর নিচে = সাধারণ সমকক্ষদের চেয়ে সস্তা। যেমন ০.৭× মানে খাতের মধ্যমার চেয়ে ৩০% কম P/E।",
  eps_growth: "আগের বছরের তুলনায় শেয়ারপ্রতি আয়। যেমন +২০% YoY = আয় ২০% বেড়েছে।",
  most_watched: "যেসব নাম সবচেয়ে বেশি মানুষ ওয়াচলিস্টে যোগ করেছে।",
  most_discussed: "গত ২ দিনে সবচেয়ে বেশি কমিউনিটি পোস্ট হওয়া নাম।",
  attention_rising:
    "এই শেয়ারের নিজের স্বাভাবিক হারের চেয়ে অনেক বেশি আলোচনা। যেমন ৩× স্বাভাবিক = দৈনিক স্বাভাবিকের তিন গুণ।",
  quiet_accumulation:
    "অর্থ ঢুকছে (ধনাত্মক CMF) এবং ভলিউমও নিশ্চিত করছে (OBV উপরে উঠছে — ভলিউম দামের আগে) অথচ দাম এখনো স্থির, ৫০-দিনের গড়ের ~১০% মধ্যে। 'নীরব ভিত্তিতে কেনা' — মুভের আগে স্মার্ট মানি যা খোঁজে। স্থির দামের লাইনের পাশে জোরালো-প্রবাহ ট্যাগই ইঙ্গিত। এটি ডাইভারজেন্স, নিশ্চয়তা নয়। পরামর্শ নয়।",
  foreign_buying:
    "বিদেশি বিনিয়োগকারীরা শেষ প্রকাশের পর মালিকানা বাড়িয়েছে কীভাবে। pp = শতাংশ পয়েন্ট (+৫ pp ≈ ১০% থেকে ১৫% মালিকানা)। লাইন = ঐ সময়ের দাম; ডট = প্রতি প্রকাশে অংশ (হোভার করলে সংখ্যা)। 'since' তারিখ তুলনার বিন্দু — প্রকাশ বছরে কয়েকবার হয়, প্রতিদিন নয়। ইতিহাস, পূর্বাভাস নয়।",
  institutional_buying:
    "স্থানীয় প্রতিষ্ঠান (মিউচুয়াল ফান্ড, অ্যাসেট ম্যানেজার) শেষ প্রকাশের পর মালিকানা বাড়িয়েছে কীভাবে। নিচে বিপরীতটির জন্য 'প্রাতিষ্ঠানিক বিক্রি' দেখুন — একই ক্যাটাগরির ভিন্ন হোল্ডাররা একসাথে দুই দিকেই যেতে পারে। pp = শতাংশ পয়েন্ট (+৫ pp ≈ কোম্পানির ৫ পয়েন্ট অংশ বেড়েছে)। লাইন = ঐ সময়ের দাম; ডট = প্রতি প্রকাশে অংশ। ইতিহাস, পূর্বাভাস নয়।",
  institutional_selling:
    "স্থানীয় প্রতিষ্ঠান (মিউচুয়াল ফান্ড, অ্যাসেট ম্যানেজার) শেষ প্রকাশের পর মালিকানা কমিয়েছে কীভাবে। নিচের স্পনসর/পরিচালক থেকে আলাদা, পৃথকভাবে প্রকাশিত একটি গ্রুপ — ফান্ড অনেক সময় সাধারণ কারণেও (রিব্যালান্সিং, রিডেম্পশন) অংশ কমায়, শুধু আস্থা হারানো নয়। pp = শতাংশ পয়েন্ট। লাইন = ঐ সময়ের দাম; ডট = প্রতি প্রকাশে অংশ। ইতিহাস, পূর্বাভাস নয়।",
  sponsor_selling:
    "স্পনসর/পরিচালক — কোম্পানির নিজস্ব অভ্যন্তরীণরা — শেষ প্রকাশের পর নিজেদের অংশ কমিয়েছেন। pp = কোম্পানির কত শতাংশ পয়েন্ট ছেড়েছেন। অভ্যন্তরীণদের নিজের কোম্পানি বিক্রি একটি প্রকাশিত তথ্য যা পড়ে দেখা উচিত (কেন? কার কাছে?), আর এক প্রিন্টের চেয়ে ধারাবাহিক স্ট্রিক বেশি গুরুত্বপূর্ণ। এটি নিজে বিক্রির সংকেত নয়।",
  most_active:
    "আজ অর্থমূল্যে সবচেয়ে বেশি লেনদেন (দাম × ভলিউম), কোটি টাকায়। ক্লাসিক 'টপ টার্নওভার' বোর্ড — দিনের কাজ যেখানে, সস্তা-ব্যস্ত নামসহ।",
  beating_market:
    "গত এক মাসে পুরো বাজারের (DSEX সূচক) চেয়ে বেশি বেড়েছে। 'আপেক্ষিক শক্তি' — বাজার যখন পড়ছে বা ধীরে উঠছে তখন উপরে ওঠা প্রকৃত শক্তির প্রাতিষ্ঠানিক ইঙ্গিত। মান = সূচককে কত % ছাড়িয়েছে।",
  momentum_12_1:
    "১২-মাসের দামের প্রবণতা, সাম্প্রতিক মাস বাদ দিয়ে (যা উল্টে যায়), তারপর অস্থিরতা দিয়ে ভাগ করা — যাতে স্থির উত্থান বুনো উত্থানের উপরে থাকে। যেমন বছরে +৮০%। কোয়ান্ট 'মোমেন্টাম' ফ্যাক্টর — তথ্যমূলক ইতিহাস, পূর্বাভাস নয়।",
  quality_roe:
    "রিটার্ন অন ইকুইটি = মুনাফা ÷ শেয়ারহোল্ডার মূলধন (EPS ÷ শেয়ারপ্রতি NAV)। বেশি = বইমূল্যের প্রতি টাকায় বেশি মুনাফা। যেমন ২৫% ≈ ৳১০০ নিট সম্পদে বছরে ৳২৫ আয়। মানের চিহ্ন, কেনার সংকেত নয়।",
  low_volatility:
    "গত এক বছরে দৈনিক দামের ওঠানামার বার্ষিক আকার। কম = বেশি স্থির। যেমন ১৫% শান্ত, ৬০% বুনো। স্থির মানে বেশি রিটার্ন নয় — শুধু মসৃণ যাত্রা।",
};
for (const type of PATTERN_ORDER) {
  SCREEN_HELP_BN[`chart_pattern_${type}`] =
    "নিশ্চিত সুইং হাই/লো থেকে তৈরি। এটি প্রথাগত টেকনিক্যাল অ্যানালাইসিস — DSE-তে দাম পূর্বাভাসে প্রমাণিত নয় (আমাদের নিজস্ব গবেষণায় সম্পর্কিত মোমেন্টাম ফ্যাক্টর বরং ক্ষতি করেছে)। বর্ণনামূলক জ্যামিতি, কখনো সংকেত নয়। বোর্ডের শিরোনামে ট্যাপ করুন এই প্যাটার্নের মানে ও 'সাধারণত কী হয়' কী বলে আর কী বলে না তা জানতে।";
}

// Localized tooltip text for a screen (falls back to English, then to the screen's own description).
export function screenHelp(key: string, lang: Lang): string | undefined {
  return (lang === "bn" ? SCREEN_HELP_BN[key] : undefined) ?? SCREEN_HELP[key];
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const monthIdx = (iso: string) => Number(iso.split("-")[1]) - 1; // parse directly, no timezone shift
const shortMonth = (iso: string) => MONTHS[monthIdx(iso)] ?? "?";
const monthYy = (iso: string) => `${shortMonth(iso)},${iso.slice(2, 4)}`; // "2026-04-30" → "Apr,26"

// Format a screen's metric for display, based on its value_label.
export function fmtValue(label: string, v: number): string {
  if (label === "RSI") return v.toFixed(0);
  if (label === "CMF") return v.toFixed(2);
  if (label === "yield") return `${v.toFixed(1)}%`;
  if (label.includes("sector")) return `${v.toFixed(2)}×`;
  if (label.includes("avg vol") || label.includes("usual"))
    return `${v.toFixed(1)}x`;
  if (label === "watchers" || label === "posts") return v.toFixed(0);
  if (label === "score") return `${v.toFixed(0)}/100`;
  if (label === "turnover")
    return `৳${v.toLocaleString(undefined, { maximumFractionDigits: v >= 10 ? 0 : 1 })} Cr`;
  if (label === "pp") return `${v >= 0 ? "+" : ""}${v.toFixed(1)} pp`;
  if (label === "ROE" || label === "volatility") return `${v.toFixed(1)}%`;
  if (label === "momentum") return `${v >= 0 ? "+" : ""}${v.toFixed(0)}%`;
  if (label === "vs market") return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
  if (label.includes("%")) return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
  return v.toFixed(2);
}

function takaMn(mn: number | null | undefined): string {
  if (mn == null) return "—";
  if (mn >= 10)
    return `৳${(mn / 10).toLocaleString(undefined, { maximumFractionDigits: mn >= 100 ? 0 : 1 })}Cr`;
  return `৳${(mn * 10).toLocaleString(undefined, { maximumFractionDigits: mn >= 1 ? 0 : 1 })}L`;
}

function setupTone(setup: string | null | undefined): Chip["tone"] {
  if (!setup) return "neutral";
  if (setup.includes("Clean")) return "up";
  if (setup.includes("High-risk")) return "down";
  return "neutral";
}

function setupLabel(setup: string | null | undefined, t: Tr): string | null {
  if (!setup) return null;
  if (setup.includes("Clean")) return t("setup.clean");
  if (setup.includes("High-risk")) return t("setup.risky");
  return t("setup.mixed");
}

function liquidityLabel(liquidity: string | null | undefined, t: Tr): string | null {
  if (!liquidity) return null;
  if (liquidity.includes("High-risk")) return t("liq.highRisk");
  if (liquidity.includes("Deep")) return t("liq.deep");
  if (liquidity.includes("Tradeable")) return t("liq.tradeable");
  if (liquidity.includes("Watch")) return t("liq.watchSize");
  if (liquidity.includes("Thin")) return t("liq.thin");
  return liquidity;
}

// Tone for a per-row note. Selling/pump = caution, buying/climb = positive, the rest neutral.
function noteTone(note: string): Chip["tone"] {
  const n = note.toLowerCase();
  if (n.includes("broke out down")) return "down";
  if (n.includes("broke out up")) return "up";
  if (n.includes("forming")) return "neutral"; // chart pattern not yet resolved either way
  if (n.includes("pump") || n.includes("selling")) return "down";
  if (n.includes("buying")) return "up";
  if (n.includes("volatile") || n === "heavy volume") return "neutral";
  return "up";
}

// A short, plain-language reading of the screen's jargon metric — descriptive facts only, never a
// cue to act. Returns null for metrics that are already self-explanatory (raw % / counts).
interface Chip {
  word: string;
  tone: "up" | "down" | "neutral";
}
type Tr = (key: string) => string;

export function metricChip(label: string, v: number, t: Tr): Chip | null {
  const w = (key: string, tone: Chip["tone"]) => ({ word: t(key), tone });
  if (label === "CMF") {
    if (v >= 0.25) return w("mc.strongInflow", "up");
    if (v >= 0.05) return w("mc.inflow", "up");
    if (v <= -0.25) return w("mc.strongOutflow", "down");
    if (v <= -0.05) return w("mc.outflow", "down");
    return w("mc.flatFlow", "neutral");
  }
  if (label === "RSI") {
    if (v >= 70) return w("mc.overbought", "neutral");
    if (v <= 30) return w("mc.oversold", "neutral");
    if (v >= 55) return w("mc.strongMomentum", "neutral");
    if (v <= 45) return w("mc.weakMomentum", "neutral");
    return w("mc.neutral", "neutral");
  }
  if (label.includes("avg vol") || label.includes("usual")) {
    if (v >= 3) return w("mc.veryHeavy", "neutral");
    if (v >= 2) return w("mc.heavyVolume", "neutral");
    return w("mc.active", "neutral");
  }
  if (label === "yield") return w(v >= 8 ? "mc.highYield" : "mc.paysDividend", "neutral");
  if (label.includes("sector")) return w("mc.cheaperPeers", "neutral");
  if (label === "% YoY") return w(v >= 50 ? "mc.fastGrowth" : "mc.growing", "up");
  if (label === "pp") {
    if (v < 0) return w("mc.reducing", "down"); // sponsor selling / distribution rows
    return w(v >= 3 ? "mc.accumulating" : "mc.buying", "up");
  }
  if (label === "ROE") return w(v >= 20 ? "mc.highlyProfitable" : "mc.profitable", "neutral");
  if (label === "volatility") return w(v < 25 ? "mc.verySteady" : "mc.steady", "neutral");
  if (label === "vs market") return w("mc.outperforming", "up");
  return null;
}

// Plain header for the rightmost (metric) column.
export function metricHeader(label: string, t: Tr): string {
  if (label === "CMF") return t("mh.moneyFlow");
  if (label === "RSI") return t("mh.momentum");
  if (label.includes("avg vol") || label.includes("usual")) return t("mh.volume");
  if (label === "yield") return t("mh.yield");
  if (label.includes("sector")) return t("mh.vsSector");
  if (label === "% YoY") return t("mh.epsGrowth");
  if (label === "watchers") return t("mh.watchers");
  if (label === "posts") return t("mh.posts");
  if (label === "turnover") return t("mh.turnover");
  if (label === "pp") return t("mh.bigMoney");
  if (label === "momentum") return t("mh.trend");
  if (label === "vs market") return t("mh.vsDsex");
  if (label === "ROE") return t("mh.roe") === "mh.roe" ? "ROE" : t("mh.roe");
  if (label === "volatility") return t("mh.volatility");
  if (label === "score") return t("mh.strength");
  if (label.includes("%")) return t("mh.change");
  return label;
}

const toneCls = (t: Chip["tone"]) =>
  t === "up" ? "text-up" : t === "down" ? "text-down" : "text-fg";

// Backend row-note words (momentum / volume / ownership tags) → Bangla. Unknown notes pass through.
const NOTE_BN: Record<string, string> = {
  "Steady climb": "স্থির ঊর্ধ্বগতি",
  Climbing: "উঠছে",
  "Volatile climb": "অস্থির ঊর্ধ্বগতি",
  "Possible pump": "সম্ভাব্য পাম্প",
  "Heavy buying": "ভারী ক্রয়",
  "Heavy selling": "ভারী বিক্রয়",
  "Heavy volume": "ভারী ভলিউম",
  "Buying more": "আরও কিনছে",
  "Started buying": "কেনা শুরু",
  "Selling more": "আরও বিক্রি",
  "Started selling": "বিক্রি শুরু",
  Buying: "কিনছে",
  Selling: "বিক্রি করছে",
};
// Each chart_pattern_* board is now titled by the specific shape (e.g. "Ascending Triangle"), so
// a row's note is just its status ("forming" / "broke out up" / "broke out down") — generated from
// lib/patterns.ts (single source of truth) rather than hand-typed.
for (const status of ["forming", "confirmed_breakout_up", "confirmed_breakout_down"] as const) {
  NOTE_BN[PATTERN_STATUS_LABEL[status].en] = PATTERN_STATUS_LABEL[status].bn;
}
const noteWord = (note: string, lang: Lang) => (lang === "bn" ? (NOTE_BN[note] ?? note) : note);

// One row, shared by the Markets cards and the explore page so they read identically.
// Trend-consistency cue: one dot per lookback (3M·6M·12M). Green = solidly climbing that window,
// muted = flat, red = down. All three green → the uptrend is broad/durable; only the long window
// green → an older move that's cooling. Exact numbers are on the 3M/6M/12M toggle.
const MOM_STRONG = 15; // % return over a window to count as "solidly climbing"
function momColor(m: number | null): string {
  if (m == null) return "var(--color-muted)";
  if (m >= MOM_STRONG) return "var(--color-up)";
  if (m >= 0) return "var(--color-muted)";
  return "var(--color-down)";
}
function MomentumDots({ h }: { h: MomHorizons }) {
  const dots: [string, number | null][] = [
    ["3M", h.m3],
    ["6M", h.m6],
    ["12M", h.m12],
  ];
  const title = dots
    .map(([lbl, m]) => `${lbl} ${m == null ? "—" : `${m >= 0 ? "+" : ""}${m}%`}`)
    .join(" · ");
  return (
    <span className="flex items-center gap-1 mt-1" title={title} aria-label={`Trend by window: ${title}`}>
      {dots.map(([lbl, m]) => (
        <span
          key={lbl}
          className="w-1.5 h-1.5 rounded-full"
          style={{ backgroundColor: momColor(m), opacity: m == null ? 0.4 : 1 }}
        />
      ))}
    </span>
  );
}

// Ownership trend as direction dots (not a line — a line reads like price). One dot per disclosure:
// green = stake rose vs the prior disclosure, red = fell, grey = flat or the baseline (no prior).
function ownDotColor(curr: number, prev: number | undefined): string {
  if (prev === undefined || curr === prev) return "var(--color-muted)";
  return curr > prev ? "var(--color-up)" : "var(--color-down)";
}
function OwnershipDots({ flow, dates }: { flow: number[]; dates: string[] }) {
  const title = flow
    .map((v, i) => `${dates[i] ? shortMonth(dates[i]) : "?"}: ${v}%`)
    .join("  ·  ");
  return (
    <span
      title={title}
      aria-label={`Stake trend: ${title}`}
      className="inline-flex items-center gap-1 mt-1"
    >
      {flow.map((v, i) => (
        <span
          key={i}
          className="w-1.5 h-1.5 rounded-full"
          style={{ backgroundColor: ownDotColor(v, i > 0 ? flow[i - 1] : undefined) }}
        />
      ))}
    </span>
  );
}

function DetailStat({ label, value, tone }: { label: string; value: string; tone?: Chip["tone"] }) {
  return (
    <div className="rounded-xl bg-card border border-border p-2 min-w-0">
      <div className="text-[10px] uppercase tracking-wide text-muted truncate">{label}</div>
      <div className={`text-sm font-bold tnum mt-0.5 truncate ${tone ? toneCls(tone) : ""}`}>
        {value}
      </div>
    </div>
  );
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-lg bg-surface/70 border border-border px-2.5 py-2">
      <div className="text-[10px] uppercase tracking-wide text-muted truncate">{label}</div>
      <div className="text-[12px] font-semibold text-text truncate tnum">{value}</div>
    </div>
  );
}

function signedPct(v: number, digits = 1): string {
  return `${v >= 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

function priceMoveText(item: ScreenItem, lang: Lang): string | null {
  if (item.change_1d == null) return null;
  return lang === "bn" ? `আজ দাম ${signedPct(item.change_1d)}` : `1D ${signedPct(item.change_1d)}`;
}

function priceMoveOverPeriod(item: ScreenItem, lang: Lang): string | null {
  const ps = item.period_spark ?? [];
  if (ps.length < 2 || !ps[0]) return null;
  const move = Math.round((ps[ps.length - 1] / ps[0] - 1) * 100);
  return lang === "bn" ? `ঐ সময়ে দাম ${signedPct(move, 0)}` : `Price over period ${signedPct(move, 0)}`;
}

function stakeContextChip(flow: number[], dates: string[], idx: number, lang: Lang): string | null {
  if (flow[idx] == null) return null;
  const when = dates[idx] ? monthYy(dates[idx]) : "";
  const label = idx === flow.length - 1 ? (lang === "bn" ? "সর্বশেষ" : "Latest") : (lang === "bn" ? "আগে" : "Previous");
  return `${label}${when ? ` ${when}` : ""} ${flow[idx].toFixed(2)}%`;
}

function rowReasonStem(screen: Screen, item: ScreenItem, lang: Lang): string {
  const metric = fmtValue(screen.value_label, item.value);
  const title = screenTitle(screen, lang);
  if (lang === "bn") {
    switch (screen.key) {
      case "institutional_buying":
      case "institutional_selling":
        return `প্রতিষ্ঠানের মালিকানা ${metric} ${item.value >= 0 ? "বেড়েছে" : "কমেছে"}`;
      case "foreign_buying":
        return `বিদেশি মালিকানা ${metric} ${item.value >= 0 ? "বেড়েছে" : "কমেছে"}`;
      case "sponsor_selling":
        return `স্পনসর/পরিচালকদের অংশ ${metric} কমেছে`;
      case "value_vs_sector":
        return `P/E খাতের মধ্যমার ${metric}`;
      case "dividend_yield":
        return `সর্বশেষ নগদ লভ্যাংশের ইল্ড ${metric}`;
      case "quality_roe":
        return `ROE ${metric}`;
      case "eps_growth":
        return `EPS বছরওয়ারি ${metric}`;
      case "beating_market":
        return `DSEX-কে ${metric} ছাড়িয়েছে`;
      case "momentum_12_1":
        return `ঝুঁকি-সমন্বিত মোমেন্টাম ${metric}`;
      case "low_volatility":
        return `বার্ষিক ওঠানামা ${metric}`;
      case "most_active":
        return `আজকের টার্নওভার ${metric}`;
      case "unusual_volume":
        return `স্বাভাবিকের ${metric} ভলিউম`;
      case "most_discussed":
        return `গত ২ দিনে ${metric} পোস্ট`;
      case "most_watched":
        return `${metric} জনের ওয়াচলিস্টে`;
      case "attention_rising":
        return `আলোচনা স্বাভাবিকের ${metric}`;
      case "near_support":
        return `সাপোর্টের ${metric} উপরে`;
      case "near_resistance":
        return `রেজিস্ট্যান্সের ${metric} নিচে`;
      case "near_52w_high":
        return `৫২-সপ্তাহের সর্বোচ্চ থেকে ${metric}`;
      case "near_52w_low":
        return `৫২-সপ্তাহের সর্বনিম্ন থেকে ${metric}`;
      case "oversold":
      case "overbought":
        return `RSI ${metric}`;
      case "accumulation":
        return `CMF ${metric} - অর্থ ঢুকছে`;
      case "distribution":
        return `CMF ${metric} - অর্থ বেরোচ্ছে`;
      case "quiet_accumulation":
        return `দাম শান্ত, কিন্তু অর্থপ্রবাহে সঞ্চয়ের ইঙ্গিত`;
      default:
        return `${title}: ${metricHeader(screen.value_label, () => screen.value_label)} ${metric}`;
    }
  }
  switch (screen.key) {
    case "institutional_buying":
    case "institutional_selling":
      return `Institutions changed stake by ${metric}`;
    case "sponsor_selling":
      return `Sponsors/directors reduced their stake by ${metric}`;
    case "foreign_buying":
      return `Foreign investors changed stake by ${metric}`;
    case "value_vs_sector":
      return `P/E is ${metric} of the sector median`;
    case "beating_market":
      return `Beat DSEX by ${metric}`;
    case "unusual_volume":
      return `${metric} normal volume`;
    default:
      return `${title}: ${metricHeader(screen.value_label, () => screen.value_label)} ${metric}`;
  }
}

function rowReason(screen: Screen, item: ScreenItem, lang: Lang, t: Tr): string {
  const parts = [
    rowReasonStem(screen, item, lang),
    priceMoveText(item, lang),
    item.adtv_mn != null ? `${t("liq.adtv")} ${takaMn(item.adtv_mn)}` : null,
    item.safe_order_mn != null ? `${t("rowDetails.order")} ${takaMn(item.safe_order_mn)}` : null,
    item.category ? `${t("liq.cat")} ${item.category}` : null,
  ];
  return parts.filter(Boolean).join(" · ");
}

function metricDetailLabel(screen: Screen, lang: Lang): string {
  if (lang === "bn") {
    switch (screen.key) {
      case "institutional_buying":
      case "institutional_selling":
      case "foreign_buying":
      case "sponsor_selling":
        return "মালিকানা পরিবর্তন";
      case "value_vs_sector":
        return "P/E বনাম খাত";
      case "dividend_yield":
        return "ডিভিডেন্ড ইল্ড";
      case "quality_roe":
        return "ROE";
      case "eps_growth":
        return "EPS বৃদ্ধি";
      case "beating_market":
        return "DSEX-এর তুলনায়";
      case "momentum_12_1":
        return "মোমেন্টাম";
      case "low_volatility":
        return "অস্থিরতা";
      case "most_active":
        return "টার্নওভার";
      case "unusual_volume":
        return "ভলিউম বনাম গড়";
      case "most_discussed":
        return "পোস্ট";
      case "most_watched":
        return "ওয়াচার";
      case "attention_rising":
        return "আলোচনা বনাম গড়";
      case "near_support":
        return "সাপোর্ট থেকে";
      case "near_resistance":
        return "রেজিস্ট্যান্স থেকে";
      case "near_52w_high":
        return "৫২W হাই থেকে";
      case "near_52w_low":
        return "৫২W লো থেকে";
      case "oversold":
      case "overbought":
        return "RSI";
      case "accumulation":
      case "distribution":
      case "quiet_accumulation":
        return "মানি ফ্লো";
      default:
        return "বোর্ড মেট্রিক";
    }
  }
  switch (screen.key) {
    case "institutional_buying":
    case "institutional_selling":
    case "foreign_buying":
    case "sponsor_selling":
      return "Stake change";
    case "value_vs_sector":
      return "P/E vs sector";
    case "dividend_yield":
      return "Dividend yield";
    case "quality_roe":
      return "ROE";
    case "eps_growth":
      return "EPS growth";
    case "beating_market":
      return "Vs DSEX";
    case "momentum_12_1":
      return "Momentum";
    case "low_volatility":
      return "Volatility";
    case "most_active":
      return "Turnover";
    case "unusual_volume":
      return "Volume vs avg";
    case "most_discussed":
      return "Posts";
    case "most_watched":
      return "Watchers";
    case "attention_rising":
      return "Chatter vs avg";
    case "near_support":
      return "Above support";
    case "near_resistance":
      return "Below resistance";
    case "near_52w_high":
      return "From 52W high";
    case "near_52w_low":
      return "From 52W low";
    case "oversold":
    case "overbought":
      return "RSI";
    case "accumulation":
    case "distribution":
    case "quiet_accumulation":
      return "Money flow";
    default:
      return "Board metric";
  }
}

function ctaTitle(code: string, lang: Lang): string {
  return lang === "bn"
    ? `$${code}-এর চার্ট ও পূর্ণ বিশ্লেষণ দেখুন`
    : `See chart and full analysis for $${code}`;
}

function detailContext(screen: Screen, item: ScreenItem, lang: Lang) {
  const metric = fmtValue(screen.value_label, item.value);
  const flow = item.flow ?? [];
  const dates = item.flow_dates ?? [];
  const prevStake = flow.length >= 2 ? stakeContextChip(flow, dates, flow.length - 2, lang) : null;
  const latestStake = flow.length >= 1 ? stakeContextChip(flow, dates, flow.length - 1, lang) : null;
  const periodMove = priceMoveOverPeriod(item, lang);
  const ctx = (body: string, checks: string[], chips: (string | null)[] = []) => ({
    body,
    checks,
    chips: chips.filter((v): v is string => Boolean(v)),
  });

  if (lang === "bn") {
    switch (screen.key) {
      case "institutional_buying":
      case "institutional_selling":
        return ctx(
          "নতুন প্রকাশে প্রতিষ্ঠানের অংশ বদলেছে। এটি দৈনিক ফ্লো নয়, তাই দামের প্রতিক্রিয়া, খবর, ভলিউম ও লিকুইডিটি মিলিয়ে পড়ুন।",
          ["মালিকানার তারিখ", "দামের প্রতিক্রিয়া", "খবর/ঘোষণা", "অর্ডার সাইজ"],
          [prevStake, latestStake, periodMove],
        );
      case "foreign_buying":
        return ctx(
          "বিদেশি মালিকানা বদল শক্তিশালী সংকেত হতে পারে, কিন্তু এটি প্রকাশভিত্তিক ডেটা। দাম, খবর ও লিকুইডিটির সাথে মিলিয়ে দেখুন।",
          ["মালিকানার তারিখ", "দামের প্রতিক্রিয়া", "ঘোষণা", "লিকুইডিটি"],
          [prevStake, latestStake, periodMove],
        );
      case "value_vs_sector":
        return ctx(
          "১.০x মানে খাতের মধ্যম P/E। এর নিচে সস্তা, কিন্তু আয় দুর্বল হলে বা ঝুঁকি থাকলে এটি ভ্যালু ট্র্যাপও হতে পারে।",
          ["EPS ট্রেন্ড", "সেক্টর তুলনা", "খবর/ঝুঁকি", "দাম কত উঠেছে"],
          [`বর্তমান ${metric}`, "সীমা 1.0x"],
        );
      case "dividend_yield":
        return ctx(
          "এটি সর্বশেষ ঘোষিত নগদ লভ্যাংশের ইল্ড। ভবিষ্যৎ লভ্যাংশ নিশ্চিত করে না; EPS, NAV, পেআউট ও রেকর্ড ডেট দেখুন।",
          ["EPS কভার করছে?", "রেকর্ড ডেট", "পেআউট ইতিহাস", "দাম সমন্বয়"],
          [`ইল্ড ${metric}`, "অতীত নগদ লভ্যাংশ"],
        );
      case "quality_roe":
        return ctx(
          "ROE দেখায় শেয়ারহোল্ডার মূলধনের প্রতি টাকায় কত মুনাফা হচ্ছে। একবারের লাভ বা অতিরিক্ত ঋণ আছে কি না মিলিয়ে দেখুন।",
          ["EPS/NAV", "ধারাবাহিকতা", "ঋণ/ঝুঁকি", "সেক্টর তুলনা"],
          [`ROE ${metric}`],
        );
      case "eps_growth":
        return ctx(
          "EPS বৃদ্ধি মানে আয় আগের বছরের তুলনায় বেড়েছে। এটি ধারাবাহিক কিনা এবং দাম ইতিমধ্যে বেশি উঠে গেছে কিনা দেখুন।",
          ["ত্রৈমাসিক ধারাবাহিকতা", "একবারের আয়?", "P/E", "খবর"],
          [`বৃদ্ধি ${metric}`],
        );
      case "beating_market":
        return ctx(
          "DSEX-এর চেয়ে বেশি ওঠা আপেক্ষিক শক্তির ইঙ্গিত। শক্তি টেকসই কিনা বুঝতে ট্রেন্ড, ভলিউম ও খবর একসাথে দেখুন।",
          ["ট্রেন্ড", "ভলিউম", "সাপোর্ট/রেজিস্ট্যান্স", "খবর"],
          [`DSEX থেকে ${metric} বেশি`, priceMoveText(item, lang)],
        );
      case "unusual_volume":
      case "most_active":
        return ctx(
          "ব্যস্ততা দেখায় আজ কোথায় টাকা ঘুরছে। শুধু ভলিউম যথেষ্ট নয়; দাম কোন দিকে যাচ্ছে এবং খবর আছে কি না দেখুন।",
          ["দামের দিক", "ঘোষণা/খবর", "স্বাভাবিক ভলিউম", "অর্ডার সাইজ"],
          [item.turnover_mn != null ? `টার্নওভার ${takaMn(item.turnover_mn)}` : null, item.adtv_mn != null ? `ADTV ${takaMn(item.adtv_mn)}` : null],
        );
      case "momentum_12_1":
      case "top_gainers":
      case "top_losers":
      case "near_52w_high":
      case "near_52w_low":
        return ctx(
          "মোমেন্টাম শক্তি দেখায়, কিন্তু দ্রুত ওঠা শেয়ারে ফিরে আসার ঝুঁকি থাকে। ট্রেন্ডের ধারাবাহিকতা ও নিকটবর্তী লেভেল দেখুন।",
          ["৩M/৬M/১২M ট্রেন্ড", "ভলিউম", "নিকটবর্তী লেভেল", "খবর"],
          [priceMoveText(item, lang), metric],
        );
      case "near_support":
      case "near_resistance":
      case "oversold":
      case "overbought":
      case "uptrend":
        return ctx(
          "এটি টেকনিক্যাল অবস্থান। সাপোর্ট, রেজিস্ট্যান্স বা RSI একা সিদ্ধান্ত নয়; ভলিউম, খবর ও ঝুঁকি সীমা মিলিয়ে পড়ুন।",
          ["লেভেল", "ভলিউম", "খবর", "রিস্ক লিমিট"],
          [`মেট্রিক ${metric}`, priceMoveText(item, lang)],
        );
      case "accumulation":
      case "distribution":
      case "quiet_accumulation":
        return ctx(
          "মানি ফ্লো দামের সাথে ভলিউম মিলিয়ে চাপ বোঝায়। এটি ইঙ্গিত, প্রমাণ নয়; ব্রেকআউট, খবর এবং লিকুইডিটি দিয়ে নিশ্চিত করুন।",
          ["দাম কি নিশ্চিত করছে?", "ভলিউম", "ব্রেকআউট", "খবর"],
          [`CMF ${metric}`, priceMoveText(item, lang)],
        );
      case "most_discussed":
      case "attention_rising":
      case "most_watched":
        return ctx(
          "কমিউনিটি আগ্রহ ট্রাফিক ও আলোচনার গতি দেখায়, কিন্তু শব্দ বেশি হতে পারে। বাস্তব খবর, দাম ও লিকুইডিটি যাচাই করুন।",
          ["আসল খবর", "দামের দিক", "লিকুইডিটি", "আলোচনার মান"],
          [`বোর্ড মেট্রিক ${metric}`, priceMoveText(item, lang)],
        );
      case "low_volatility":
        return ctx(
          "কম অস্থিরতা মানে দাম তুলনামূলক শান্ত। এটি বেশি রিটার্নের গ্যারান্টি নয়; আয়, ডিভিডেন্ড ও ট্রেন্ড মিলিয়ে দেখুন।",
          ["আয়", "ডিভিডেন্ড", "ট্রেন্ড", "লিকুইডিটি"],
          [`অস্থিরতা ${metric}`, priceMoveText(item, lang)],
        );
      default:
        return ctx(
          screenHelp(screen.key, lang) ?? screenDesc(screen, lang),
          ["খবর", "দামের দিক", "লিকুইডিটি"],
          [metric, priceMoveText(item, lang)],
        );
    }
  }

  switch (screen.key) {
    case "institutional_buying":
    case "institutional_selling":
    case "foreign_buying":
      return ctx(
        "Ownership updates are disclosure-based, not daily flow. Read the stake change together with price reaction, news, volume, and liquidity.",
        ["Disclosure date", "Price reaction", "News", "Order size"],
        [prevStake, latestStake, periodMove],
      );
    case "value_vs_sector":
      return ctx(
        "1.0x is the sector median P/E. Below 1.0x is cheaper than peers, but weak earnings or risk can still make it a value trap.",
        ["EPS trend", "Sector comparison", "News/risk", "Price stretch"],
        [`Current ${metric}`, "Line 1.0x"],
      );
    default:
      return ctx(
        screenHelp(screen.key, lang) ?? screenDesc(screen, lang),
        ["News", "Price action", "Liquidity"],
        [metric, priceMoveText(item, lang)],
      );
  }
}

function ScreenRowSheet({
  item,
  screen,
  setupChip,
  chip,
  onClose,
}: {
  item: ScreenItem;
  screen: Screen;
  setupChip: Chip | null;
  chip: Chip | null;
  onClose: () => void;
}) {
  const { t, lang } = useLang();
  const localizedTitle = lang === "bn" ? (SCREEN_BN[screen.key]?.t ?? screen.title) : screen.title;
  const liquidity = liquidityLabel(item.liquidity, t);
  const why = rowReason(screen, item, lang, t);
  const context = detailContext(screen, item, lang);
  const metricLabel = metricDetailLabel(screen, lang);
  const priceTone: Chip["tone"] | undefined =
    item.change_1d == null ? undefined : item.change_1d >= 0 ? "up" : "down";
  const executionRows = [
    item.adtv_mn != null ? { label: t("liq.adtv"), value: takaMn(item.adtv_mn) } : null,
    item.safe_order_mn != null ? { label: t("rowDetails.order"), value: takaMn(item.safe_order_mn) } : null,
    item.turnover_mn != null ? { label: t("rowDetails.turnover"), value: takaMn(item.turnover_mn) } : null,
    item.category ? { label: t("liq.cat"), value: item.category } : null,
    item.market_cap_mn != null
      ? { label: t("rowDetails.marketCap"), value: takaMn(item.market_cap_mn) }
      : null,
    item.free_float_cap_mn != null
      ? { label: t("rowDetails.freeFloat"), value: takaMn(item.free_float_cap_mn) }
      : null,
  ].filter((row): row is { label: string; value: string } => Boolean(row));

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/55" onClick={onClose}>
      <div
        className="w-full max-w-md bg-surface border border-border rounded-t-2xl max-h-[86vh] overflow-y-auto shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-4 pb-0">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-[10px] uppercase tracking-wide text-muted">
                {t("rowDetails.title")}
              </div>
              <div className="flex items-center gap-2 min-w-0">
                <div className="text-lg font-extrabold text-text truncate">${item.code}</div>
                {setupChip && (
                  <span
                    className={`rounded-full border border-border bg-card px-2 py-0.5 text-[10px] font-semibold shrink-0 ${toneCls(setupChip.tone)}`}
                  >
                    {setupChip.word}
                  </span>
                )}
              </div>
              <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-muted">
                <span className="truncate">{item.name || item.code}</span>
                <span className="text-border">•</span>
                <span className="text-accent">{localizedTitle}</span>
              </div>
            </div>
            <button onClick={onClose} className="text-muted text-sm px-2" aria-label={t("common.close")}>
              {t("common.close")}
            </button>
          </div>

          <div className="mt-3 grid grid-cols-2 gap-2">
            <DetailStat label={t("rowDetails.price")} value={taka(item.last_close)} tone={priceTone} />
            <DetailStat
              label={metricLabel}
              value={fmtValue(screen.value_label, item.value)}
              tone={chip?.tone}
            />
            {item.change_1d != null && (
              <DetailStat
                label="1D"
                value={`${item.change_1d >= 0 ? "+" : ""}${item.change_1d.toFixed(1)}%`}
                tone={priceTone}
              />
            )}
            {liquidity && <DetailStat label={t("rowDetails.liquidity")} value={liquidity} />}
          </div>

          <section className="mt-4 rounded-xl bg-accent/8 border border-accent/25 p-3">
            <div className="text-[10px] uppercase tracking-wide text-muted">
              {t("rowDetails.summary")}
            </div>
            <p className="mt-1 text-[14px] leading-snug text-text">{why}</p>
          </section>

          <section className="mt-3 rounded-xl bg-card/60 border border-border p-3">
            <div className="flex items-center justify-between gap-2">
              <div className="text-[11px] uppercase tracking-wide text-muted">
                {t("rowDetails.context")}
              </div>
              <span className="shrink-0 rounded-full border border-border bg-surface px-2 py-0.5 text-[10px] text-accent">
                {localizedTitle}
              </span>
            </div>
            <p className="mt-1.5 text-[12px] leading-snug text-text/90">{context.body}</p>
            {context.checks.length > 0 && (
              <div className="mt-3">
                <div className="text-[10px] uppercase tracking-wide text-muted">
                  {t("rowDetails.checks")}
                </div>
                <div className="mt-2 grid grid-cols-2 gap-1.5">
                  {context.checks.map((check) => (
                    <div key={check} className="flex items-center gap-1.5 text-[11px] text-muted">
                      <span className="h-1.5 w-1.5 rounded-full bg-accent shrink-0" />
                      <span className="truncate">{check}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {context.chips.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {context.chips.map((c) => (
                  <span
                    key={c}
                    className="rounded-full bg-surface border border-border px-2.5 py-1 text-[11px] text-muted"
                  >
                    {c}
                  </span>
                ))}
              </div>
            )}
          </section>

          {executionRows.length > 0 && (
            <section className="mt-3 rounded-xl bg-card/40 border border-border p-3">
              <div className="text-[11px] uppercase tracking-wide text-muted">
                {t("rowDetails.execution")}
              </div>
              <div className="mt-2 grid grid-cols-2 gap-2">
                {executionRows.map((r) => (
                  <MiniMetric key={`${r.label}-${r.value}`} label={r.label} value={r.value} />
                ))}
              </div>
              {item.safe_order_mn != null && (
                <p className="mt-2 text-[11px] leading-snug text-muted">{t("rowDetails.orderHelp")}</p>
              )}
            </section>
          )}

          {item.catalyst && (
            <section className="mt-3 rounded-xl bg-card/40 border border-border p-3">
              <div className="text-[11px] uppercase tracking-wide text-muted">
                {t("rowDetails.catalyst")}
              </div>
              <p className="mt-1 text-[13px] leading-snug text-accent">
                {item.catalyst_category} · {item.catalyst_date}
              </p>
              <p className="mt-0.5 text-[12px] leading-snug text-muted">{item.catalyst}</p>
            </section>
          )}
        </div>

        <div className="sticky bottom-0 mt-4 bg-surface/95 backdrop-blur border-t border-border p-4">
          <Link
            to={`/s/${item.code}`}
            className="block text-center bg-accent text-bg font-extrabold rounded-xl py-3 text-sm"
          >
            {ctaTitle(item.code, lang)} →
          </Link>
          <p className="mt-2 text-center text-[11px] leading-snug text-muted">{t("rowDetails.ctaSub")}</p>
        </div>
      </div>
    </div>
  );
}

export function ScreenRow({
  item,
  screen,
  rank,
}: {
  item: ScreenItem;
  screen: Screen;
  rank?: number;
}) {
  const { t, lang } = useLang();
  const isMover = screen.key === "top_gainers" || screen.key === "top_losers";
  const chip = item.note
    ? { word: noteWord(item.note, lang), tone: noteTone(item.note) }
    : isMover
      ? null
      : metricChip(screen.value_label, item.value, t);
  const showName = item.name && item.name !== item.code;
  // Ownership screens: show the stake trend as dots + the comparison month (no year — short label).
  const fdates = item.flow_dates ?? [];
  const isOwnership = !!(item.flow && item.flow.length);
  const sinceMonth = fdates.length >= 2 ? monthYy(fdates[fdates.length - 2]) : null;
  const setup = setupLabel(item.setup_quality, t);
  const setupChip = setup ? { word: setup, tone: setupTone(item.setup_quality) } : null;
  const liquidity = liquidityLabel(item.liquidity, t);
  const [open, setOpen] = useState(false);
  // Tooltip explaining the price line on ownership rows: what period + how price moved over it.
  const ps = item.period_spark ?? [];
  let priceTitle: string | undefined;
  if (isOwnership && ps.length >= 2 && sinceMonth) {
    const move = ps[0] ? Math.round((ps[ps.length - 1] / ps[0] - 1) * 100) : 0;
    priceTitle = `Price since ${sinceMonth}: ${taka(ps[0])} → ${taka(ps[ps.length - 1])} (${move >= 0 ? "+" : ""}${move}%)`;
  }
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="w-full text-left flex items-center gap-3 py-2 border-t border-border/60 first:border-t-0"
      >
        <span className="flex items-center gap-2 min-w-0 flex-1">
          {rank != null && (
            <span className="text-[11px] text-muted tnum w-5 shrink-0">{rank}</span>
          )}
          <CompanyLogo code={item.code} size={26} />
          <span className="flex flex-col min-w-0 gap-0.5">
            <span className="flex items-center gap-1.5 min-w-0">
              <span className="font-bold text-[13px]">${item.code}</span>
              {setupChip && (
                <span
                  className={`text-[9px] font-semibold rounded-full px-1.5 py-0.5 ${toneCls(setupChip.tone)} bg-card border border-border shrink-0`}
                >
                  {setupChip.word}
                </span>
              )}
            </span>
            {showName && <span className="text-[11px] text-muted truncate">{item.name}</span>}
            {(liquidity || item.category) && (
              <span className="text-[10px] text-muted leading-snug truncate">
                {liquidity}
                {item.category && (
                  <>
                    {liquidity ? " · " : ""}
                    {t("liq.cat")} {item.category}
                  </>
                )}
              </span>
            )}
          </span>
        </span>
        {/* Always a price line. For ownership it spans the move window (the title explains the period). */}
        <span title={priceTitle} className="shrink-0 inline-flex">
          <Sparkline
            data={isOwnership && item.period_spark?.length ? item.period_spark : item.spark}
          />
        </span>
        <span className="flex items-stretch gap-3 shrink-0 text-right">
          <span className="flex flex-col items-end justify-center">
            <span className="text-xs text-muted tnum">{taka(item.last_close)}</span>
            {item.change_1d != null && (
              <span
                className={`text-[11px] tnum ${item.change_1d >= 0 ? "text-up" : "text-down"}`}
              >
                {item.change_1d >= 0 ? "+" : ""}
                {item.change_1d.toFixed(1)}%
              </span>
            )}
          </span>
          <span
            className={`flex flex-col items-end justify-center ${isOwnership ? "min-w-[92px]" : "w-20"}`}
          >
            {isMover ? (
              <span
                className={`text-xs font-semibold tnum ${item.value >= 0 ? "text-up" : "text-down"}`}
              >
                {fmtValue(screen.value_label, item.value)}
              </span>
            ) : chip ? (
              <>
                <span className={`text-xs font-semibold ${toneCls(chip.tone)}`}>{chip.word}</span>
                <span className="flex items-baseline gap-1.5 whitespace-nowrap text-[10px] text-muted">
                  <span className="tnum">{fmtValue(screen.value_label, item.value)}</span>
                  {sinceMonth && <span>· since {sinceMonth}</span>}
                </span>
                {isOwnership && <OwnershipDots flow={item.flow ?? []} dates={fdates} />}
                {item.horizons && <MomentumDots h={item.horizons} />}
              </>
            ) : (
              <span className="text-xs font-semibold text-accent tnum">
                {fmtValue(screen.value_label, item.value)}
              </span>
            )}
          </span>
        </span>
      </button>
      {open && (
        <ScreenRowSheet
          item={item}
          screen={screen}
          setupChip={setupChip}
          chip={chip}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}

// Display order + labels. "technical" is collapsed by default (advanced).
const GROUPS: { id: string; labelKey: string; advanced?: boolean }[] = [
  { id: "movers", labelKey: "group.movers" },
  { id: "community", labelKey: "group.community" },
  { id: "value", labelKey: "group.value" },
  { id: "technical", labelKey: "group.technical", advanced: true },
];

// Default "Today's Market" — the high-signal, distinctive boards a DSE investor actually decides on,
// anchored by the "Active today" engine (rendered above these as the live what's-moving view). We
// deliberately do NOT lead with top gainers/losers/most-active: every DSE portal shows those, the
// "Active today" engine already covers what's genuinely moving (liquidity-gated, not thin-circuit
// noise), and they live under the Momentum lens / All boards for anyone who wants them. Each card
// here is a different decision axis — smart money, relative strength, income, value × quality, buzz.
// Merit order (2026-07 review): ownership intelligence first, income + value core, community
// pulse, and relative strength LAST — momentum was the one factor our DSE study found harmful,
// so it never headlines. sponsor_selling = the disclosure-synthesis red-flag board.
// institutional_buying/selling sit side by side deliberately: same disclosed category, opposite
// direction — a user asked why only sponsors got a "selling" board when institutions can exit too.
const FOCUS_KEYS = [
  "institutional_buying", // smart money — what institutions are accumulating
  "institutional_selling", // ...and, just as real, what they're distributing
  "sponsor_selling", // insiders reducing — the red-flag counterweight
  "dividend_yield", // trailing cash income — BD investors care
  "value_vs_sector", // cheap vs its sector...
  "quality_roe", // ...paired with quality so it's not a value trap
  "most_discussed", // the community pulse
  "beating_market", // relative strength vs the DSEX — context only, demoted
];

// "What are you looking for?" — curate the screens down to a goal, so a beginner sees relevant
// boards instead of twenty. Orientation, not deletion ("All boards" still shows everything, grouped).
const LENSES: { id: string; icon: string; labelKey: string; blurbKey: string; keys: string[] }[] = [
  {
    id: "momentum",
    icon: "📈",
    labelKey: "lens.momentum",
    blurbKey: "lens.momentum.blurb",
    keys: [
      "momentum_12_1",
      "beating_market",
      "top_gainers",
      "most_active",
      "near_52w_high",
      "unusual_volume",
    ],
  },
  {
    id: "value",
    icon: "🏷️",
    labelKey: "lens.value",
    blurbKey: "lens.value.blurb",
    keys: [
      "value_vs_sector",
      "quality_roe",
      "eps_growth",
      "dividend_yield",
      "quiet_accumulation",
      "near_52w_low",
    ],
  },
  {
    id: "smart",
    icon: "🏦",
    labelKey: "lens.smart",
    blurbKey: "lens.smart.blurb",
    keys: [
      "institutional_buying",
      "institutional_selling",
      "foreign_buying",
      "quiet_accumulation",
      "unusual_volume",
    ],
  },
  {
    id: "dividend",
    icon: "💵",
    labelKey: "lens.dividend",
    blurbKey: "lens.dividend.blurb",
    keys: ["dividend_yield", "quality_roe", "low_volatility"],
  },
  {
    id: "steady",
    icon: "🌊",
    labelKey: "lens.steady",
    blurbKey: "lens.steady.blurb",
    keys: ["low_volatility", "quality_roe", "uptrend", "dividend_yield"],
  },
  {
    id: "patterns",
    icon: "📐",
    labelKey: "lens.patterns",
    blurbKey: "lens.patterns.blurb",
    // One board per shape (not a single combined list) — a user asked for this split so each
    // pattern reads as its own thing rather than everything blended into one strength-sorted list.
    keys: PATTERN_ORDER.map((type) => `chart_pattern_${type}`),
  },
];

// FreshnessTag moved to ../components/FreshnessTag.tsx (shared with Ideas) — see that file for
// the "why" (the RANKINGS on /screens boards are EOD-anchored regardless of the current session
// state; a user asked why a bare '1D' tag on the Ideas page didn't say when it was calculated).

// First-run framing: sets the mental model (descriptive, not tips) and teaches the ⓘ gesture, once.
function MarketIntro() {
  const { t } = useLang();
  const [seen, setSeen] = useState(() => localStorage.getItem("bulls.mktIntro") === "1");
  if (seen) return null;
  const dismiss = () => {
    localStorage.setItem("bulls.mktIntro", "1");
    setSeen(true);
  };
  return (
    <div className="bg-accent/5 border border-accent/30 rounded-2xl p-3">
      <div className="flex items-center gap-2 text-sm font-semibold">
        🎓 {t("mktIntro.title")}
      </div>
      <ul className="mt-2 flex flex-col gap-1 text-[12px] text-muted leading-relaxed">
        <li>• {t("mktIntro.p1")}</li>
        <li>• {t("mktIntro.p2")}</li>
        <li>• {t("mktIntro.p3")}</li>
      </ul>
      <button
        onClick={dismiss}
        className="mt-2 text-[11px] font-semibold text-accent border border-accent/40 rounded-full px-3 py-1"
      >
        {t("mktIntro.dismiss")}
      </button>
    </div>
  );
}

export function screenTitle(s: Screen, lang: Lang): string {
  return lang === "bn" ? (SCREEN_BN[s.key]?.t ?? s.title) : s.title;
}
export function screenDesc(s: Screen, lang: Lang): string {
  return lang === "bn" ? (SCREEN_BN[s.key]?.d ?? s.description) : s.description;
}

// Momentum-family boards carry the honest caution: our own factor study found trend-chasing
// HURT returns on DSE (IC −0.077 @60d). Descriptive context, never a hunting ground.
const MOMENTUM_CAUTION_KEYS = new Set(["beating_market", "momentum_12_1", "near_52w_high"]);
const momentumCaution = (lang: string) =>
  lang === "bn"
    ? "সতর্কতা: আমাদের নিজস্ব DSE গবেষণায় (২০২৪–২৬) ট্রেন্ড-চেজিং ক্ষতি করেছে। এটি প্রেক্ষাপট, শিকারের তালিকা নয়।"
    : "Heads-up: our own DSE study (2024–26) found trend-chasing hurt returns. This is context, not a hunting list.";

function ScreenCard({ s }: { s: Screen }) {
  const { t, lang } = useLang();
  const [showAll, setShowAll] = useState(false);
  const visible = showAll ? s.items : s.items.slice(0, 5);
  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <div className="flex flex-wrap items-center gap-1.5">
        <div className="font-semibold text-sm">{screenTitle(s, lang)}</div>
        <InfoTip text={screenHelp(s.key, lang) ?? screenDesc(s, lang)} lessonId={SCREEN_LESSON[s.key]} />
        <EvidenceNote
          evidence={s.evidence}
          extra={MOMENTUM_CAUTION_KEYS.has(s.key) ? momentumCaution(lang) : undefined}
        />
      </div>
      <div className="text-[11px] text-muted">{screenDesc(s, lang)}</div>
      <div className="mt-2 flex justify-between text-[10px] uppercase tracking-wide text-muted/70 pb-1">
        <span>{t("col.symbol")}</span>
        <span className="flex gap-3">
          <span>{t("col.price")}</span>
          <span className="w-20 text-right">{metricHeader(s.value_label, t)}</span>
        </span>
      </div>
      <div className="flex flex-col">
        {visible.map((it) => (
          <ScreenRow key={it.code} item={it} screen={s} />
        ))}
      </div>
      {!showAll && s.items.length > 5 && (
        <button
          onClick={() => setShowAll(true)}
          className="block w-full text-center text-[11px] font-semibold text-accent mt-2 pt-2 border-t border-border/60"
        >
          {t("viewMore")} ({s.items.length - 5})
        </button>
      )}
      {showAll && (
        <Link
          to={`/markets/${s.key}`}
          className="block text-center text-[11px] text-accent mt-2 pt-2 border-t border-border/60"
        >
          {t("viewMore")} →
        </Link>
      )}
    </div>
  );
}

function LiquidityGuideSheet({ onClose }: { onClose: () => void }) {
  const { t } = useLang();
  const setupRows: { label: string; body: string; tone: Chip["tone"] }[] = [
    { label: t("setup.clean"), body: t("liqGuide.setupCleanBody"), tone: "up" },
    { label: t("setup.mixed"), body: t("liqGuide.setupMixedBody"), tone: "neutral" },
    { label: t("setup.risky"), body: t("liqGuide.setupRiskyBody"), tone: "down" },
  ];
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/55" onClick={onClose}>
      <section
        className="w-full max-w-md bg-surface border border-border rounded-t-2xl p-4 max-h-[82vh] overflow-y-auto shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="font-semibold text-sm">{t("liqGuide.title")}</div>
            <p className="mt-1 text-[12px] text-muted leading-relaxed">{t("liqGuide.subtitle")}</p>
          </div>
          <button
            onClick={onClose}
            className="text-muted text-sm px-2 shrink-0"
            aria-label={t("common.close")}
          >
            {t("common.close")}
          </button>
        </div>

        <div className="mt-3 flex flex-col gap-3">
          <div className="border-l-2 border-accent pl-3">
            <div className="text-[11px] font-semibold text-text">{t("liqGuide.adtvTitle")}</div>
            <p className="mt-0.5 text-[12px] text-muted leading-relaxed">
              {t("liqGuide.adtvBody")}
            </p>
          </div>
          <div className="border-l-2 border-accent pl-3">
            <div className="text-[11px] font-semibold text-text">{t("liqGuide.orderTitle")}</div>
            <p className="mt-0.5 text-[12px] text-muted leading-relaxed">
              {t("liqGuide.orderBody")}
            </p>
          </div>
        </div>

        <div className="mt-3 pt-3 border-t border-border/60 flex flex-col gap-3">
          <div>
            <div className="text-[11px] font-semibold text-up">
              {t("liqGuide.liquidExampleTitle")}
            </div>
            <p className="mt-0.5 text-[12px] text-muted leading-relaxed">
              {t("liqGuide.liquidExampleBody")}
            </p>
          </div>
          <div>
            <div className="text-[11px] font-semibold text-down">
              {t("liqGuide.thinExampleTitle")}
            </div>
            <p className="mt-0.5 text-[12px] text-muted leading-relaxed">
              {t("liqGuide.thinExampleBody")}
            </p>
          </div>
        </div>

        <div className="mt-3 pt-3 border-t border-border/60">
          <div className="text-[11px] font-semibold text-text">{t("liqGuide.setupTitle")}</div>
          <div className="mt-2 flex flex-col gap-2">
            {setupRows.map((row) => (
              <div key={row.label} className="rounded-xl border border-border bg-card/50 p-2">
                <span
                  className={`inline-flex rounded-full border border-border bg-card px-2 py-0.5 text-[10px] font-semibold ${toneCls(row.tone)}`}
                >
                  {row.label}
                </span>
                <p className="mt-1 text-[12px] text-muted leading-relaxed">{row.body}</p>
              </div>
            ))}
          </div>
          <p className="mt-2 text-[10px] text-muted">{t("liqGuide.footer")}</p>
        </div>
      </section>
    </div>
  );
}

function LiquidityGuide() {
  const { t } = useLang();
  const [open, setOpen] = useState(false);
  return (
    <>
      <section className="bg-surface border border-border rounded-2xl p-3 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="font-semibold text-sm">{t("liqGuide.title")}</div>
          <p className="mt-0.5 text-[12px] text-muted leading-snug">{t("liqGuide.compact")}</p>
        </div>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="shrink-0 rounded-full border border-accent/60 bg-accent/10 px-3 py-1.5 text-[11px] font-semibold text-accent"
        >
          {t("liqGuide.open")}
        </button>
      </section>
      {open && <LiquidityGuideSheet onClose={() => setOpen(false)} />}
    </>
  );
}

export function Markets() {
  const { t } = useLang();
  useSeo({
    title: {
      bn: "মার্কেট স্ক্রিন — DSE গেইনার, লুজার, ভলিউম, ভ্যালু | Bulls of Dhaka",
      en: "Market screens — DSE gainers, losers, volume, value | Bulls of Dhaka",
    },
    description: {
      bn: "ঢাকা স্টক এক্সচেঞ্জের রেডিমেড স্ক্রিন: টপ গেইনার/লুজার, অস্বাভাবিক ভলিউম, সস্তা vs খাত, প্রাতিষ্ঠানিক প্রবাহ, চার্ট প্যাটার্ন। বর্ণনামূলক তথ্য, পরামর্শ নয়।",
      en: "Ready-made Dhaka Stock Exchange screens: top gainers/losers, unusual volume, cheap-vs-sector, institutional flow, chart patterns. Descriptive, not advice.",
    },
  });
  const [data, setData] = useState<ScreensResponse | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [lens, setLens] = useState("focus");

  useEffect(() => {
    api
      .screens()
      .then(setData)
      .catch(() => setData({ as_of: null, screens: [] }));
  }, []);

  if (data === null) return <Spinner />;
  const live = data.screens.filter((s) => s.items.length > 0);
  const byKey = new Map(live.map((s) => [s.key, s]));
  const activeLens = LENSES.find((l) => l.id === lens);
  const isFocus = lens === "focus";
  const isAllBoards = lens === "all";
  const focusScreens = FOCUS_KEYS.map((k) => byKey.get(k)).filter((s): s is Screen => Boolean(s));

  return (
    <div className="flex flex-col gap-3">
      {/* Pinned below the app header — same treatment as the Ideas/Symbol tab bars. */}
      <div
        className="sticky z-10 -mx-3 px-3 py-1.5 bg-bg/95 backdrop-blur flex gap-2 overflow-x-auto"
        style={{ top: "var(--app-header-h, 96px)" }}
      >
        {[{ id: "focus", icon: "", labelKey: "lens.focus" }, ...LENSES, { id: "all", icon: "", labelKey: "lens.all" }].map((l) => (
          <button
            key={l.id}
            onClick={() => setLens(l.id)}
            className={`whitespace-nowrap text-xs font-semibold px-3 py-1.5 rounded-full border ${
              lens === l.id ? "text-accent border-accent bg-accent/10" : "text-muted border-border"
            }`}
          >
            {l.icon ? `${l.icon} ` : ""}
            {t(l.labelKey)}
          </button>
        ))}
      </div>

      <div className="flex items-center justify-between px-1">
        <div className="text-[11px] text-muted">
          {isFocus ? t("markets.focusBlurb") : activeLens ? t(activeLens.blurbKey) : t("markets.browseAll")}
        </div>
        <FreshnessTag asOf={data.as_of} quoteAsOf={data.quote_as_of} />
      </div>
      <div className="text-[10px] text-muted px-1 -mt-1">{t("mkt.rankNote")}</div>

      <MarketPulse />
      {isFocus && <MarketIntro />}
      {isFocus && <WatchToday asOf={data.as_of} />}
      {isFocus && <EarningsWeek />}
      {(isFocus || isAllBoards) && <SectorHeat />}

      {isFocus
        ? focusScreens.map((s) => <ScreenCard key={s.key} s={s} />)
        : activeLens
        ? activeLens.keys
            .map((k) => byKey.get(k))
            .filter((s): s is Screen => Boolean(s))
            .map((s) => <ScreenCard key={s.key} s={s} />)
        : GROUPS.map((g) => {
        const items = live.filter((s) => s.group === g.id);
        if (!items.length) return null;
        if (g.advanced) {
          return (
            <div key={g.id} className="flex flex-col gap-3">
              <button
                onClick={() => setShowAdvanced((v) => !v)}
                className="text-[11px] uppercase tracking-wide text-muted text-left px-1"
              >
                {showAdvanced ? "▾" : "▸"} {t(g.labelKey)}
              </button>
              {showAdvanced &&
                items.map((s) => <ScreenCard key={s.key} s={s} />)}
            </div>
          );
        }
        return (
          <div key={g.id} className="flex flex-col gap-3">
            <div className="flex items-center justify-between px-1">
              <div className="text-[11px] uppercase tracking-wide text-muted">{t(g.labelKey)}</div>
              <Link to={`/markets/${items[0].key}`} className="text-[11px] text-accent">
                {t("viewMore")}
              </Link>
            </div>
            {items.map((s) => (
              <ScreenCard key={s.key} s={s} />
            ))}
          </div>
        );
      })}

      <LiquidityGuide />
      <p className="text-[10px] text-muted px-1 pb-2">{t("markets.footer")}</p>
    </div>
  );
}
