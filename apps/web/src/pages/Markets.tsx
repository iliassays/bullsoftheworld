import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  api,
  type MomHorizons,
  type Screen,
  type ScreenItem,
  type ScreensResponse,
} from "../lib/api";
import { Spinner, taka } from "../components/ui";
import { InfoTip } from "../components/InfoTip";
import { Sparkline } from "../components/Sparkline";
import { SectorHeat } from "../components/SectorHeat";
import { WatchToday } from "../components/WatchToday";
import { type Lang, useLang } from "../lib/i18n";
import { SCREEN_BN, SCREEN_LESSON } from "../lib/lessons";

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
    "How foreign investors changed their ownership since the prior disclosure. Use the Buying / Selling chip to flip between accumulation and distribution. pp = percentage points (+5 pp ≈ they went from owning 10% to 15%). The line is the share price over that window; the dots are the stake at each disclosure (hover for figures). The 'since' date is the comparison point — disclosures come a few times a year, not daily. History, not a forecast.",
  institutional_buying:
    "How local institutions (mutual funds, asset managers) changed their ownership since the prior disclosure. Use the Buying / Selling chip to flip between accumulation and distribution. pp = percentage points (+5 pp ≈ stake up 5 of the company's points). The line is the share price over that window; the dots are the stake at each disclosure. History, not a forecast.",
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
    "বিদেশি বিনিয়োগকারীরা শেষ প্রকাশের পর মালিকানা কীভাবে বদলেছে। ক্রয়/বিক্রয় চিপ দিয়ে সঞ্চয় ও বিক্রির মধ্যে পাল্টান। pp = শতাংশ পয়েন্ট (+৫ pp ≈ ১০% থেকে ১৫% মালিকানা)। লাইন = ঐ সময়ের দাম; ডট = প্রতি প্রকাশে অংশ (হোভার করলে সংখ্যা)। 'since' তারিখ তুলনার বিন্দু — প্রকাশ বছরে কয়েকবার হয়, প্রতিদিন নয়। ইতিহাস, পূর্বাভাস নয়।",
  institutional_buying:
    "স্থানীয় প্রতিষ্ঠান (মিউচুয়াল ফান্ড, অ্যাসেট ম্যানেজার) শেষ প্রকাশের পর মালিকানা কীভাবে বদলেছে। ক্রয়/বিক্রয় চিপ দিয়ে পাল্টান। pp = শতাংশ পয়েন্ট (+৫ pp ≈ কোম্পানির ৫ পয়েন্ট অংশ বেড়েছে)। লাইন = ঐ সময়ের দাম; ডট = প্রতি প্রকাশে অংশ। ইতিহাস, পূর্বাভাস নয়।",
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
  if (label === "turnover")
    return `৳${v.toLocaleString(undefined, { maximumFractionDigits: v >= 10 ? 0 : 1 })} Cr`;
  if (label === "pp") return `${v >= 0 ? "+" : ""}${v.toFixed(1)} pp`;
  if (label === "ROE" || label === "volatility") return `${v.toFixed(1)}%`;
  if (label === "momentum") return `${v >= 0 ? "+" : ""}${v.toFixed(0)}%`;
  if (label === "vs market") return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
  if (label.includes("%")) return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
  return v.toFixed(2);
}

// Tone for a per-row note. Selling/pump = caution, buying/climb = positive, the rest neutral.
function noteTone(note: string): Chip["tone"] {
  const n = note.toLowerCase();
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
  if (label === "pp") return w(v >= 3 ? "mc.accumulating" : "mc.buying", "up");
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
  // Tooltip explaining the price line on ownership rows: what period + how price moved over it.
  const ps = item.period_spark ?? [];
  let priceTitle: string | undefined;
  if (isOwnership && ps.length >= 2 && sinceMonth) {
    const move = ps[0] ? Math.round((ps[ps.length - 1] / ps[0] - 1) * 100) : 0;
    priceTitle = `Price since ${sinceMonth}: ${taka(ps[0])} → ${taka(ps[ps.length - 1])} (${move >= 0 ? "+" : ""}${move}%)`;
  }
  return (
    <Link
      to={`/s/${item.code}`}
      className="flex items-center gap-3 py-2 border-t border-border/60 first:border-t-0"
    >
      <span className="flex items-center gap-2 min-w-0 flex-1">
        {rank != null && (
          <span className="text-[11px] text-muted tnum w-5 shrink-0">{rank}</span>
        )}
        <span className="flex flex-col min-w-0">
          <span className="font-bold text-[13px]">${item.code}</span>
          {showName && <span className="text-[11px] text-muted truncate">{item.name}</span>}
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
    </Link>
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
const FOCUS_KEYS = [
  "institutional_buying", // smart money — what institutions are accumulating
  "beating_market", // relative strength vs the DSEX
  "dividend_yield", // trailing cash income — BD investors care
  "value_vs_sector", // cheap vs its sector...
  "quality_roe", // ...paired with quality so it's not a value trap
  "most_discussed", // the community pulse
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
    keys: ["institutional_buying", "foreign_buying", "quiet_accumulation", "unusual_volume"],
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
];

export function screenTitle(s: Screen, lang: Lang): string {
  return lang === "bn" ? (SCREEN_BN[s.key]?.t ?? s.title) : s.title;
}
export function screenDesc(s: Screen, lang: Lang): string {
  return lang === "bn" ? (SCREEN_BN[s.key]?.d ?? s.description) : s.description;
}

function ScreenCard({ s }: { s: Screen }) {
  const { t, lang } = useLang();
  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <div className="flex items-center gap-1.5">
        <div className="font-semibold text-sm text-accent">{screenTitle(s, lang)}</div>
        <InfoTip text={screenHelp(s.key, lang) ?? screenDesc(s, lang)} lessonId={SCREEN_LESSON[s.key]} />
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
        {s.items.slice(0, 6).map((it) => (
          <ScreenRow key={it.code} item={it} screen={s} />
        ))}
      </div>
      {s.items.length >= 6 && (
        <Link
          to={`/markets/${s.key}`}
          className="block text-center text-[11px] text-accent mt-2 pt-2 border-t border-border/60"
        >
          {t("viewMore")}
        </Link>
      )}
    </div>
  );
}

export function Markets() {
  const { t } = useLang();
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
      <div className="text-[11px] uppercase tracking-wide text-muted px-1">
        {t("markets.lookingFor")}
      </div>
      <div className="flex gap-2 overflow-x-auto pb-1">
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
        {data.as_of && (
          <div className="text-[10px] text-muted shrink-0 ml-2">
            {t("asOf")} {data.as_of} {t("close")}
          </div>
        )}
      </div>

      {isFocus && <WatchToday />}
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

      <p className="text-[10px] text-muted px-1 pb-2">{t("markets.footer")}</p>
    </div>
  );
}
