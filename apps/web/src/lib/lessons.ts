// Short, example-driven lessons: not "what is X" (the tooltip covers that) but "how do traders
// actually USE X to decide" — with a worked, real-ticker example. Descriptive education, never advice.
import type { Lang } from "./i18n";

export interface Lesson {
  title: string;
  what: string;
  use: string;
  watch: string;
  example: string;
}

export const LESSONS: Record<string, Lesson> = {
  momentum: {
    title: "Momentum (12-month trend)",
    what: "How strongly a stock has trended over the past year, skipping the last month (which tends to reverse).",
    use: "Momentum traders ride stocks that keep climbing. They pair it with the long-term trend (above the 200-day average) and look to enter on small dips rather than chase a spike.",
    watch: "Momentum can reverse hard — especially in a market like DSE. A huge recent jump plus a high RSI means 'stretched', not 'strong'.",
    example: "SQURPHARMA up ~40% over the year and still above its 200-day average looks like an intact uptrend. A 600% penny-stock spike is far more likely a pump than a trend.",
  },
  value_pe: {
    title: "Value (cheap vs sector)",
    what: "Price-to-earnings (P/E) compared with the stock's own sector. Below the sector median = cheaper than peers.",
    use: "Value investors buy sound companies trading below their peers, betting the gap closes. They confirm earnings are real and steady, not collapsing.",
    watch: "'Cheap' can mean the market sees trouble — a value trap. Always check WHY it's cheap, and pair it with quality (ROE) and the news.",
    example: "A profitable bank at P/E 8 while its sector sits at 12 looks genuinely cheap. A loss-making firm at a low P/E is cheap for a reason.",
  },
  roe: {
    title: "Quality (return on equity)",
    what: "ROE = profit ÷ shareholder capital — how much profit the company earns on each taka of net worth.",
    use: "Quality investors favour consistently high ROE (15%+): a sign of a strong, efficient business. It pairs well with value to avoid traps.",
    watch: "One great year isn't quality — look for consistency. Sky-high ROE built on heavy debt is riskier than it looks.",
    example: "GP and RECKITT earn 40%+ ROE — classic quality names. A 3% ROE business is barely beating a bank deposit.",
  },
  dividend: {
    title: "Dividend yield",
    what: "Last year's cash dividend as a percentage of today's price.",
    use: "Income investors hold steady payers for regular cash, checking the company can keep paying (profits, manageable debt).",
    watch: "A very high yield usually means the price crashed (a trap), not generosity. Bonus (stock) dividends aren't cash.",
    example: "A stable company paying 6% on a steady price is real income. A '25% yield' on a ৳3 collapsed stock is a warning sign.",
  },
  volatility: {
    title: "Volatility (steadiness)",
    what: "How big the day-to-day price swings are over the past year.",
    use: "Conservative investors prefer low-volatility names for a calmer ride that's easier to hold through ups and downs — often blue chips.",
    watch: "Low volatility means smoother, not higher returns. Extremely low can also signal thin trading.",
    example: "RECKITT and MARICO swing ~12% a year (steady); a hot small-cap can swing 60%+.",
  },
  rsi: {
    title: "RSI (overbought / oversold)",
    what: "A 0–100 momentum gauge: above 70 = overbought (run up fast), below 30 = oversold (fallen fast).",
    use: "Mean-reversion traders watch the extremes as a heads-up — not a trigger. In a strong trend, overbought can stay overbought for a while.",
    watch: "RSI alone isn't a signal. Oversold works better on beaten-down, thinly-traded names; overbought matters most right after a big run.",
    example: "RSI 75 on a stock that just spiked = stretched; many traders wait for it to cool before entering.",
  },
  moneyflow: {
    title: "Money flow (CMF)",
    what: "Whether recent volume is pushing the price up (buyers in control) or down (sellers in control).",
    use: "It confirms a move: a rising price with money flowing in is more convincing than a rise on no real buying.",
    watch: "It's a short-term read and flips quickly — use it to confirm, not to predict.",
    example: "A breakout with strong inflow is more believable than one on thin volume.",
  },
  volume: {
    title: "Volume & turnover",
    what: "How much is trading versus normal (unusual volume), or in total money terms (most active).",
    use: "A volume spike means something is happening — news, a breakout, or a pump. Traders find out WHY before acting.",
    watch: "Big volume on a penny stock can be a pump. Look at turnover (money), not just share count, and find the reason.",
    example: "4× the usual volume on a results day is real interest; 4× on no news is suspicious.",
  },
  smartmoney: {
    title: "Institutions & foreign buying",
    what: "Whether institutions and foreign investors raised their stake at the last monthly disclosure.",
    use: "Retail often treats 'smart money' accumulation as a vote of confidence in a name.",
    watch: "Disclosures are monthly and backward-looking — it's history, not a live signal, and big players can be wrong too.",
    example: "Institutions adding 5 pp over a month suggests growing conviction — but the data is already a few weeks old.",
  },
};

// Bangla lessons — clear, simple retail phrasing (not literal MT). Tickers stay in English.
export const LESSONS_BN: Record<string, Lesson> = {
  momentum: {
    title: "মোমেন্টাম (১২-মাসের প্রবণতা)",
    what: "গত এক বছরে শেয়ারটি কতটা শক্তিশালীভাবে এগিয়েছে, শেষ মাস বাদ দিয়ে (যা প্রায়ই উল্টে যায়)।",
    use: "মোমেন্টাম ট্রেডাররা যেসব শেয়ার ধারাবাহিক উঠছে সেগুলো ধরে। তারা দীর্ঘমেয়াদি প্রবণতার (২০০-দিনের গড়ের উপরে) সাথে মিলিয়ে দেখেন এবং স্পাইক ধাওয়া না করে ছোট পতনে ঢোকার চেষ্টা করেন।",
    watch: "মোমেন্টাম দ্রুত উল্টে যেতে পারে — বিশেষত DSE-র মতো বাজারে। সাম্প্রতিক বিশাল লাফ + উঁচু RSI মানে 'বেশি বেড়ে গেছে', 'শক্তিশালী' নয়।",
    example: "SQURPHARMA বছরে ~৪০% বেড়ে এখনো ২০০-দিনের গড়ের উপরে — অক্ষত ঊর্ধ্বমুখী প্রবণতা মনে হয়। কোনো পেনি স্টকের ৬০০% লাফ প্রবণতার চেয়ে পাম্প হওয়ার সম্ভাবনা বেশি।",
  },
  value_pe: {
    title: "ভ্যালু (খাতের চেয়ে সস্তা)",
    what: "শেয়ারটির P/E তার নিজের খাতের সাথে তুলনা। খাতের মধ্যমার নিচে = সমকক্ষদের চেয়ে সস্তা।",
    use: "ভ্যালু বিনিয়োগকারীরা সমকক্ষদের চেয়ে কম দামে থাকা ভালো কোম্পানি কেনেন, ব্যবধান কমবে এই আশায়। তারা যাচাই করেন আয় সত্যিকার ও স্থিতিশীল কিনা।",
    watch: "'সস্তা' মানে বাজার সমস্যা দেখছে এমন হতে পারে — ভ্যালু ট্র্যাপ। কেন সস্তা তা সবসময় যাচাই করুন, এবং মান (ROE) ও খবরের সাথে মিলিয়ে দেখুন।",
    example: "P/E ৮-এ লাভজনক একটি ব্যাংক, যেখানে খাত ১২-এ — সত্যিই সস্তা মনে হয়। কম P/E-তে লোকসানি কোম্পানি কারণ ছাড়াই সস্তা নয়।",
  },
  roe: {
    title: "মান (রিটার্ন অন ইকুইটি)",
    what: "ROE = মুনাফা ÷ শেয়ারহোল্ডারদের মূলধন — প্রতি টাকা নিট সম্পদে কোম্পানি কত মুনাফা করে।",
    use: "মান-সন্ধানী বিনিয়োগকারীরা ধারাবাহিক উঁচু ROE (১৫%+) পছন্দ করেন — শক্তিশালী, দক্ষ ব্যবসার চিহ্ন। ভ্যালুর সাথে মিলিয়ে ট্র্যাপ এড়াতে ভালো।",
    watch: "এক বছরের ভালো ফল মান নয় — ধারাবাহিকতা দেখুন। বেশি ঋণের উপর গড়া আকাশছোঁয়া ROE দেখতে যতটা ভালো ততটা ঝুঁকিপূর্ণ।",
    example: "GP ও RECKITT ৪০%+ ROE করে — ক্লাসিক মানসম্পন্ন নাম। ৩% ROE-র ব্যবসা ব্যাংক ডিপোজিটের চেয়ে সামান্য ভালো।",
  },
  dividend: {
    title: "লভ্যাংশ ইল্ড",
    what: "আজকের দামের শতাংশ হিসেবে গত বছরের নগদ লভ্যাংশ।",
    use: "আয়-সন্ধানী বিনিয়োগকারীরা নিয়মিত নগদের জন্য স্থির লভ্যাংশদাতা ধরে রাখেন, কোম্পানি দিতে পারবে কিনা (মুনাফা, সহনীয় ঋণ) যাচাই করে।",
    watch: "খুব উঁচু ইল্ড সাধারণত দাম পড়ে যাওয়ার ফল (ট্র্যাপ), উদারতা নয়। বোনাস (শেয়ার) লভ্যাংশ নগদ নয়।",
    example: "স্থির দামে ৬% দেওয়া একটি স্থিতিশীল কোম্পানি সত্যিকার আয়। ৳৩-এ ধসে পড়া শেয়ারে '২৫% ইল্ড' একটি বিপদসংকেত।",
  },
  volatility: {
    title: "অস্থিরতা (স্থিরতা)",
    what: "গত এক বছরে দৈনিক দামের ওঠানামা কতটা বড়।",
    use: "রক্ষণশীল বিনিয়োগকারীরা শান্ত যাত্রার জন্য কম-অস্থিরতার নাম পছন্দ করেন, যা ওঠানামার মধ্যেও ধরে রাখা সহজ — প্রায়ই ব্লু চিপ।",
    watch: "কম অস্থিরতা মানে মসৃণ, বেশি রিটার্ন নয়। অত্যন্ত কম মানে কম লেনদেনও বোঝাতে পারে।",
    example: "RECKITT ও MARICO বছরে ~১২% ওঠানামা করে (স্থির); কোনো গরম স্মল-ক্যাপ ৬০%+ ওঠানামা করতে পারে।",
  },
  rsi: {
    title: "RSI (অতিরিক্ত কেনা / অতিরিক্ত বিক্রি)",
    what: "০–১০০ মোমেন্টাম মাপ: ৭০-এর উপরে = অতিরিক্ত কেনা (দ্রুত বেড়েছে), ৩০-এর নিচে = অতিরিক্ত বিক্রি (দ্রুত পড়েছে)।",
    use: "মিন-রিভার্সন ট্রেডাররা চরম মানগুলো সতর্কবার্তা হিসেবে দেখেন — ট্রিগার নয়। শক্তিশালী প্রবণতায় অতিরিক্ত কেনা অবস্থা কিছুদিন থাকতে পারে।",
    watch: "শুধু RSI কোনো সংকেত নয়। অতিরিক্ত বিক্রি ভালো কাজ করে পড়ে থাকা, কম লেনদেনের নামে; অতিরিক্ত কেনা সবচেয়ে গুরুত্বপূর্ণ বড় দৌড়ের ঠিক পরে।",
    example: "সদ্য স্পাইক করা শেয়ারে RSI ৭৫ = বেশি বেড়ে গেছে; অনেক ট্রেডার ঢোকার আগে ঠান্ডা হওয়ার অপেক্ষা করেন।",
  },
  moneyflow: {
    title: "মানি ফ্লো (CMF)",
    what: "সাম্প্রতিক ভলিউম দামকে উপরে ঠেলছে (ক্রেতারা নিয়ন্ত্রণে) নাকি নিচে (বিক্রেতারা নিয়ন্ত্রণে)।",
    use: "এটি একটি মুভ নিশ্চিত করে: অর্থ ঢুকতে থাকা অবস্থায় দাম বাড়া, প্রকৃত ক্রয় ছাড়া বাড়ার চেয়ে বেশি বিশ্বাসযোগ্য।",
    watch: "এটি স্বল্পমেয়াদি পাঠ এবং দ্রুত উল্টে যায় — পূর্বাভাসের জন্য নয়, নিশ্চিত করতে ব্যবহার করুন।",
    example: "জোরালো প্রবাহসহ ব্রেকআউট পাতলা ভলিউমের ব্রেকআউটের চেয়ে বেশি বিশ্বাসযোগ্য।",
  },
  volume: {
    title: "ভলিউম ও টার্নওভার",
    what: "স্বাভাবিকের তুলনায় কতটা লেনদেন হচ্ছে (অস্বাভাবিক ভলিউম), বা মোট অর্থমূল্যে (সবচেয়ে সক্রিয়)।",
    use: "ভলিউম স্পাইক মানে কিছু ঘটছে — খবর, ব্রেকআউট, বা পাম্প। ট্রেডাররা কাজ করার আগে কেন তা বের করেন।",
    watch: "পেনি স্টকে বড় ভলিউম পাম্প হতে পারে। শুধু শেয়ার সংখ্যা নয়, টার্নওভার (অর্থ) দেখুন এবং কারণ খুঁজুন।",
    example: "ফলাফলের দিনে স্বাভাবিকের ৪× ভলিউম প্রকৃত আগ্রহ; খবর ছাড়া ৪× সন্দেহজনক।",
  },
  smartmoney: {
    title: "প্রতিষ্ঠান ও বিদেশি ক্রয়",
    what: "শেষ মাসিক প্রকাশে প্রতিষ্ঠান ও বিদেশি বিনিয়োগকারীরা তাদের অংশ বাড়িয়েছে কিনা।",
    use: "রিটেইল প্রায়ই 'স্মার্ট মানি' সঞ্চয়কে নামটির প্রতি আস্থার ভোট হিসেবে দেখে।",
    watch: "প্রকাশ মাসিক ও পেছনমুখী — এটি ইতিহাস, লাইভ সংকেত নয়, এবং বড় খেলোয়াড়রাও ভুল হতে পারে।",
    example: "এক মাসে প্রতিষ্ঠান ৫ pp যোগ করা ক্রমবর্ধমান আস্থার ইঙ্গিত — তবে ডেটা ইতিমধ্যে কয়েক সপ্তাহ পুরনো।",
  },
};

export const getLesson = (id: string, lang: Lang): Lesson | undefined =>
  (lang === "bn" ? LESSONS_BN[id] : undefined) ?? LESSONS[id];

// Which lesson backs each screen (by screen key). Screens without an entry just show the tooltip.
export const SCREEN_LESSON: Record<string, string> = {
  momentum_12_1: "momentum",
  top_gainers: "momentum",
  top_losers: "momentum",
  value_vs_sector: "value_pe",
  quality_roe: "roe",
  dividend_yield: "dividend",
  low_volatility: "volatility",
  oversold: "rsi",
  overbought: "rsi",
  accumulation: "moneyflow",
  quiet_accumulation: "moneyflow",
  distribution: "moneyflow",
  unusual_volume: "volume",
  most_active: "volume",
  foreign_buying: "smartmoney",
  institutional_buying: "smartmoney",
};

// Bangla screen titles + descriptions (the backend serves English). Keyed by screen key; a missing
// entry falls back to the backend strings. Used by Markets + the explore page.
export const SCREEN_BN: Record<string, { t: string; d: string }> = {
  top_gainers: { t: "টপ গেইনার", d: "আজ সবচেয়ে বেশি বেড়েছে" },
  top_losers: { t: "টপ লুজার", d: "আজ সবচেয়ে বেশি কমেছে" },
  most_active: { t: "সবচেয়ে সক্রিয়", d: "আজ মূল্যে সবচেয়ে বেশি লেনদেন" },
  momentum_12_1: {
    t: "সবচেয়ে শক্তিশালী প্রবণতা",
    d: "সবচেয়ে স্থির, শক্তিশালী ঊর্ধ্বমুখী প্রবণতায় থাকা শেয়ার",
  },
  unusual_volume: { t: "অস্বাভাবিক ভলিউম", d: "গড়ের তুলনায় অনেক বেশি লেনদেন" },
  beating_market: { t: "বাজারকে ছাড়িয়ে", d: "পুরো বাজারের (DSEX) চেয়ে বেশি বেড়েছে" },
  near_52w_high: { t: "৫২-সপ্তাহের সর্বোচ্চের কাছে", d: "বার্ষিক সর্বোচ্চের ৫% মধ্যে" },
  near_52w_low: { t: "৫২-সপ্তাহের সর্বনিম্নের কাছে", d: "বার্ষিক সর্বনিম্নের ৫% মধ্যে" },
  near_support: { t: "সাপোর্টের কাছে", d: "সাপোর্ট লেভেলের ঠিক উপরে লেনদেন" },
  near_resistance: { t: "রেজিস্ট্যান্সের কাছে", d: "রেজিস্ট্যান্স লেভেলের কাছে" },
  accumulation: { t: "অর্থ ঢুকছে", d: "ক্রয়চাপ — ইতিবাচক মানি ফ্লো" },
  distribution: { t: "বিক্রয়চাপ", d: "অর্থ বেরোচ্ছে (নেতিবাচক মানি ফ্লো)" },
  quiet_accumulation: { t: "নীরব সঞ্চয়", d: "দাম স্থির থাকতেই অর্থ ঢুকছে — মুভের আগের সঞ্চয়" },
  uptrend: { t: "ঊর্ধ্বমুখী প্রবণতা", d: "৫০ ও ২০০-দিনের গড়ের উপরে" },
  eps_growth: { t: "ইপিএস বৃদ্ধি", d: "আয় বছরওয়ারি বাড়ছে" },
  value_vs_sector: { t: "খাতের চেয়ে সস্তা", d: "খাতের গড় P/E-র নিচে লেনদেন" },
  quality_roe: { t: "উচ্চ রিটার্ন অন ইকুইটি", d: "শক্তিশালী মুনাফা (ROE)" },
  low_volatility: { t: "স্থির (কম অস্থিরতা)", d: "কম দৈনিক ওঠানামা" },
  dividend_yield: { t: "সর্বোচ্চ লভ্যাংশ ইল্ড", d: "আজকের দামে সর্বোচ্চ নগদ লভ্যাংশ ইল্ড" },
  foreign_buying: { t: "বিদেশি", d: "বিদেশি বিনিয়োগকারীরা শেষ প্রকাশে অংশ পরিবর্তন করেছে" },
  institutional_buying: { t: "প্রতিষ্ঠান", d: "প্রতিষ্ঠান শেষ প্রকাশে অংশ পরিবর্তন করেছে" },
  most_watched: { t: "সর্বাধিক ওয়াচড", d: "যাদের সবচেয়ে বেশি ওয়াচ করা হচ্ছে" },
  most_discussed: { t: "সর্বাধিক আলোচিত", d: "যাদের নিয়ে সবচেয়ে বেশি আলোচনা" },
  attention_rising: { t: "আলোচনা বাড়ছে", d: "স্বাভাবিকের চেয়ে অনেক বেশি আলোচনা" },
};
