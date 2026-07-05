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
  active_today: {
    title: "Active today",
    what: "Stocks trading unusually heavily versus their OWN normal — by shares (volume) and by money (turnover) — whether the price is up or down.",
    use: "It tells you where attention and money are concentrating right now, so you know what to look at first. Then you check WHY — the news/announcements — before forming any view.",
    watch: "Heavy trading shows interest, not direction: a surge can be heavy buying OR heavy selling. It is not a buy list. We show only liquid names and filter out the thin pump-prone ones, but always confirm the reason yourself.",
    example: "A blue-chip trading 4× its normal volume with ৳40cr turnover is genuinely 'in play'. A thin penny stock spiking is more likely a pump — which is exactly what the liquidity filter removes.",
  },
  smartmoney: {
    title: "Institutions & foreign ownership",
    what: "Whether institutions and foreign investors raised OR reduced their stake at the last monthly disclosure — accumulation and distribution are two separate boards.",
    use: "Retail often treats 'smart money' accumulation as a vote of confidence, and distribution as a caution flag — in a name.",
    watch: "Disclosures are monthly and backward-looking — it's history, not a live signal, big players can be wrong too, and funds sell for many routine reasons besides a change of view.",
    example: "Institutions adding 5 pp over a month suggests growing conviction; trimming 5 pp suggests the opposite — but either way the data is already a few weeks old.",
  },
  pattern_ascending_triangle: {
    title: "Ascending Triangle",
    what: "A flat resistance line capping the price, while the lows keep stepping higher — buyers stepping in earlier each time, sellers holding the same ceiling.",
    use: "Classic textbook reading: rising demand pressing against a fixed supply level often resolves upward when that ceiling finally gives way, ideally on stronger-than-usual volume.",
    watch: "This is textbook technical analysis, not proven on DSE — our own study found the related momentum factor actually hurt returns here. A flat ceiling can just as easily reject price repeatedly and never break. Confirm with the news, not the shape alone.",
    example: "A stock bouncing between a steady ৳110 ceiling and lows of ৳90, ৳95, ৳100 over a few months is textbook — if it later closes above ৳110 on above-average volume, that's the 'breakout' this pattern is named for.",
  },
  pattern_descending_triangle: {
    title: "Descending Triangle",
    what: "A flat support line holding the price up, while the highs keep stepping lower — sellers pressing in earlier each time, buyers holding the same floor.",
    use: "Classic textbook reading: the mirror of an ascending triangle — persistent selling pressure against a fixed floor often resolves downward when that floor gives way.",
    watch: "Same caveat as every pattern here: unproven on DSE data, and a floor can hold for a long time before it ever breaks, if it breaks at all. Don't treat 'shape' as destiny.",
    example: "A stock making lower highs of ৳150, ৳145, ৳140 while repeatedly finding buyers near ৳130 is a descending triangle — a later close below ৳130 is what this pattern calls a breakdown.",
  },
  pattern_channel_up: {
    title: "Rising Channel",
    what: "Two roughly parallel, rising lines — a support line and a resistance line both climbing at a similar pace, with price oscillating between them.",
    use: "Traders sometimes buy near the lower (support) line and expect a bounce toward the upper line, within an intact uptrend — as long as the channel holds.",
    watch: "A channel is just a description of recent behaviour, not a promise it continues. Prices break out of channels in both directions, and 'buy the dip' inside a channel is exactly the kind of trend-following our own DSE study found didn't pay off.",
    example: "A stock whose lows and highs have both climbed steadily for two months, staying within a consistent band, is in a rising channel.",
  },
  pattern_channel_down: {
    title: "Falling Channel",
    what: "Two roughly parallel, falling lines — support and resistance both declining at a similar pace, with price oscillating between them.",
    use: "The mirror of a rising channel: some traders watch for a break above the upper line as a possible sign the decline is stalling.",
    watch: "A persistent falling channel is still a downtrend — 'it's due for a bounce' is a feeling, not a fact this shape proves.",
    example: "A stock whose lows and highs have both declined steadily for two months, staying within a consistent band, is in a falling channel.",
  },
  pattern_channel_horizontal: {
    title: "Horizontal Channel",
    what: "Price bouncing between a roughly flat resistance level and a roughly flat support level — a trading range, not a trend.",
    use: "This is simply 'the stock isn't trending right now' — some traders watch the range edges for a bounce, others wait for a breakout in either direction before acting.",
    watch: "A range can persist for a very long time, and a range can also be quietly building toward a breakout — the shape alone doesn't tell you which.",
    example: "A stock trading between ৳100 and ৳120 for several months, repeatedly bouncing off both levels, is in a horizontal channel.",
  },
  pattern_double_top: {
    title: "Double Top",
    what: "Two comparable price peaks with a meaningful pullback between them — the price tested a level twice and couldn't clear it either time.",
    use: "Classic bearish-reversal reading: failing to make a new high twice in a row, at the same level, is read as fading momentum. The 'neckline' (the low between the two peaks) is the level some traders watch for a confirming break.",
    watch: "Two peaks can also just be normal back-and-forth in a healthy uptrend — this shape is famously prone to being read into charts after the fact. Never proven on DSE data.",
    example: "A stock rallying to ৳120, pulling back to ৳100, rallying again to ৳121, then falling — a later close below ৳100 (the neckline) is what this pattern calls a breakdown.",
  },
  pattern_double_bottom: {
    title: "Double Bottom",
    what: "Two comparable price troughs with a meaningful bounce between them — the price tested a floor twice and held both times. The mirror of a double top.",
    use: "Classic bullish-reversal reading: holding the same floor twice is read as fading selling pressure. The 'neckline' (the high between the two troughs) is the level some traders watch for a confirming break.",
    watch: "Same caveat, mirrored: two troughs can be normal noise in a downtrend, and this is not proven to predict anything on DSE data.",
    example: "A stock falling to ৳100, bouncing to ৳120, falling again to ৳99, then rising — a later close above ৳120 (the neckline) is what this pattern calls a breakout.",
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
  active_today: {
    title: "আজকের সক্রিয়",
    what: "যেসব শেয়ার নিজের স্বাভাবিকের তুলনায় অস্বাভাবিক বেশি লেনদেন হচ্ছে — শেয়ার সংখ্যায় (ভলিউম) ও অর্থে (টার্নওভার) — দাম ওঠা বা নামা যাই হোক।",
    use: "এটি দেখায় এখন কোথায় মনোযোগ ও অর্থ জমছে, তাই প্রথমে কোনদিকে তাকাবেন বুঝবেন। তারপর কোনো মত গঠনের আগে কারণ — খবর/ঘোষণা — যাচাই করুন।",
    watch: "বেশি লেনদেন আগ্রহ বোঝায়, দিক নয়: স্পাইক মানে ভারী ক্রয় বা ভারী বিক্রয় দুটোই হতে পারে। এটি কেনার তালিকা নয়। আমরা শুধু তারল্যপূর্ণ নাম দেখাই ও পাতলা পাম্প-প্রবণগুলো বাদ দিই, তবু কারণ নিজে যাচাই করুন।",
    example: "একটি ব্লু-চিপ নিজের স্বাভাবিকের ৪× ভলিউম ও ৳৪০কোটি টার্নওভারে সত্যিকারের 'সক্রিয়'। একটি পাতলা পেনি স্টকের স্পাইক বরং পাম্প — যা তারল্য ফিল্টার বাদ দেয়।",
  },
  smartmoney: {
    title: "প্রতিষ্ঠান ও বিদেশি মালিকানা",
    what: "শেষ মাসিক প্রকাশে প্রতিষ্ঠান ও বিদেশি বিনিয়োগকারীরা অংশ বাড়িয়েছে নাকি কমিয়েছে — সঞ্চয় ও বিক্রি আলাদা দুটি বোর্ড।",
    use: "রিটেইল প্রায়ই 'স্মার্ট মানি' সঞ্চয়কে আস্থার ভোট, আর বিক্রিকে সতর্কতার সংকেত হিসেবে দেখে।",
    watch: "প্রকাশ মাসিক ও পেছনমুখী — এটি ইতিহাস, লাইভ সংকেত নয়, বড় খেলোয়াড়রাও ভুল হতে পারে, আর ফান্ড অনেক সময় সাধারণ কারণেও (দৃষ্টিভঙ্গি বদল ছাড়াই) বিক্রি করে।",
    example: "এক মাসে প্রতিষ্ঠান ৫ pp যোগ করা ক্রমবর্ধমান আস্থার ইঙ্গিত; ৫ pp কমানো বিপরীত ইঙ্গিত — তবে দুই ক্ষেত্রেই ডেটা ইতিমধ্যে কয়েক সপ্তাহ পুরনো।",
  },
  pattern_ascending_triangle: {
    title: "ঊর্ধ্বমুখী ত্রিভুজ",
    what: "দাম একটি নির্দিষ্ট রেজিস্ট্যান্স লেভেলে বাধা পাচ্ছে, অথচ প্রতিটি নিম্নমুখী ধাপ আগেরটির চেয়ে উঁচুতে হচ্ছে — ক্রেতারা আগেভাগে ঢুকছে, বিক্রেতারা একই সিলিং ধরে আছে।",
    use: "প্রথাগত পাঠ: বাড়ন্ত চাহিদা একটি স্থির সরবরাহ লেভেলের বিরুদ্ধে চাপ দিলে, সেই সিলিং ভাঙলে প্রায়ই ঊর্ধ্বমুখী সমাধান হয় — বিশেষত বাড়তি ভলিউমে।",
    watch: "এটি প্রথাগত টেকনিক্যাল অ্যানালাইসিস, DSE-তে প্রমাণিত নয় — আমাদের নিজস্ব গবেষণায় সম্পর্কিত মোমেন্টাম ফ্যাক্টর বরং ক্ষতি করেছে। একটি ফ্ল্যাট সিলিং বারবার প্রত্যাখ্যানও করতে পারে, কখনো নাও ভাঙতে পারে। আকৃতি একা নয়, খবরও যাচাই করুন।",
    example: "একটি শেয়ার ৳১১০ সিলিং ও ক্রমবর্ধমান লো (৳৯০, ৳৯৫, ৳১০০) এর মধ্যে দোলাচ্ছে — এটিই এই প্যাটার্ন। পরে ৳১১০-এর উপরে বাড়তি ভলিউমে ক্লোজ করলে সেটিই 'ব্রেকআউট'।",
  },
  pattern_descending_triangle: {
    title: "নিম্নমুখী ত্রিভুজ",
    what: "দাম একটি নির্দিষ্ট সাপোর্ট লেভেলে ধরে থাকছে, অথচ প্রতিটি ঊর্ধ্বমুখী ধাপ আগেরটির চেয়ে নিচুতে হচ্ছে — বিক্রেতারা আগেভাগে ঢুকছে, ক্রেতারা একই ফ্লোর ধরে আছে।",
    use: "প্রথাগত পাঠ: ঊর্ধ্বমুখী ত্রিভুজের বিপরীত — একটি স্থির ফ্লোরের বিরুদ্ধে ধারাবাহিক বিক্রয়চাপ সেই ফ্লোর ভাঙলে প্রায়ই নিম্নমুখী সমাধান হয়।",
    watch: "একই সতর্কতা: DSE-তে অপ্রমাণিত, আর একটি ফ্লোর ভাঙার আগে অনেকদিন টিকে থাকতে পারে, কখনো নাও ভাঙতে পারে। 'আকৃতি' নিয়তি নয়।",
    example: "একটি শেয়ার ক্রমহ্রাসমান হাই (৳১৫০, ৳১৪৫, ৳১৪০) করছে অথচ বারবার ৳১৩০-এর কাছে ক্রেতা পাচ্ছে — এটি নিম্নমুখী ত্রিভুজ। পরে ৳১৩০-এর নিচে ক্লোজ করলে এই প্যাটার্ন তাকে 'ব্রেকডাউন' বলে।",
  },
  pattern_channel_up: {
    title: "ঊর্ধ্বমুখী চ্যানেল",
    what: "প্রায় সমান্তরাল দুটি ঊর্ধ্বমুখী লাইন — সাপোর্ট ও রেজিস্ট্যান্স একই গতিতে বাড়ছে, দাম দুইয়ের মাঝে দোলাচ্ছে।",
    use: "কিছু ট্রেডার নিচের (সাপোর্ট) লাইনের কাছে কেনেন এবং উপরের লাইনের দিকে বাউন্সের আশা করেন — যতক্ষণ চ্যানেল অক্ষত থাকে।",
    watch: "চ্যানেল শুধু সাম্প্রতিক আচরণের বর্ণনা, ভবিষ্যতের প্রতিশ্রুতি নয়। দাম দুই দিকেই চ্যানেল ভাঙতে পারে, আর চ্যানেলের ভেতরে 'ডিপে কেনা' ঠিক সেই ট্রেন্ড-অনুসরণ যা আমাদের DSE গবেষণায় লাভজনক পাওয়া যায়নি।",
    example: "একটি শেয়ারের লো ও হাই দুটোই দুই মাস ধরে স্থিরভাবে বেড়েছে, একটি সামঞ্জস্যপূর্ণ ব্যান্ডে থেকে — এটি ঊর্ধ্বমুখী চ্যানেল।",
  },
  pattern_channel_down: {
    title: "নিম্নমুখী চ্যানেল",
    what: "প্রায় সমান্তরাল দুটি নিম্নমুখী লাইন — সাপোর্ট ও রেজিস্ট্যান্স একই গতিতে কমছে, দাম দুইয়ের মাঝে দোলাচ্ছে।",
    use: "ঊর্ধ্বমুখী চ্যানেলের বিপরীত: কিছু ট্রেডার উপরের লাইন ভাঙাকে পতন থেমে যাওয়ার সম্ভাব্য ইঙ্গিত হিসেবে দেখেন।",
    watch: "একটি ধারাবাহিক নিম্নমুখী চ্যানেল আসলে একটি ডাউনট্রেন্ডই — 'বাউন্স করার সময় হয়েছে' একটি অনুভূতি, এই আকৃতির প্রমাণিত সত্য নয়।",
    example: "একটি শেয়ারের লো ও হাই দুটোই দুই মাস ধরে স্থিরভাবে কমেছে, একটি সামঞ্জস্যপূর্ণ ব্যান্ডে থেকে — এটি নিম্নমুখী চ্যানেল।",
  },
  pattern_channel_horizontal: {
    title: "আনুভূমিক চ্যানেল",
    what: "দাম প্রায়-ফ্ল্যাট রেজিস্ট্যান্স ও প্রায়-ফ্ল্যাট সাপোর্টের মধ্যে দোলাচ্ছে — একটি ট্রেডিং রেঞ্জ, ট্রেন্ড নয়।",
    use: "এর মানে মূলত 'শেয়ারটি এখন ট্রেন্ডে নেই' — কিছু ট্রেডার রেঞ্জের প্রান্তে বাউন্সের জন্য নজর রাখেন, অন্যরা যেকোনো দিকে ব্রেকআউটের অপেক্ষা করেন।",
    watch: "একটি রেঞ্জ অনেকদিন টিকে থাকতে পারে, আবার নীরবে ব্রেকআউটের দিকেও এগোতে পারে — শুধু আকৃতি দেখে কোনটি বলা যায় না।",
    example: "একটি শেয়ার কয়েক মাস ধরে ৳১০০ থেকে ৳১২০-এর মধ্যে লেনদেন হচ্ছে, বারবার দুই লেভেলেই বাউন্স করছে — এটি আনুভূমিক চ্যানেল।",
  },
  pattern_double_top: {
    title: "ডাবল টপ",
    what: "তুলনীয় দুটি শিখর, মাঝে একটি অর্থপূর্ণ পতনসহ — দাম একই লেভেল দুইবার পরীক্ষা করেছে এবং কোনোবারই পার হতে পারেনি।",
    use: "ক্লাসিক বিয়ারিশ-রিভার্সাল পাঠ: টানা দুইবার একই লেভেলে নতুন হাই করতে ব্যর্থ হওয়াকে দুর্বল হয়ে আসা মোমেন্টাম হিসেবে পড়া হয়। 'নেকলাইন' (দুই শিখরের মাঝের লো) হলো সেই লেভেল যা কিছু ট্রেডার নিশ্চিতকরণ ব্রেকের জন্য দেখেন।",
    watch: "দুটি শিখর একটি সুস্থ আপট্রেন্ডেও স্বাভাবিক ওঠানামা হতে পারে — এই আকৃতি ঘটনার পরে চার্টে 'দেখতে পাওয়ার' জন্য কুখ্যাত। DSE-তে কখনো প্রমাণিত নয়।",
    example: "একটি শেয়ার ৳১২০-এ উঠে, ৳১০০-এ নেমে, আবার ৳১২১-এ উঠে, তারপর পড়ছে — পরে ৳১০০ (নেকলাইন) এর নিচে ক্লোজ করলে এই প্যাটার্ন তাকে 'ব্রেকডাউন' বলে।",
  },
  pattern_double_bottom: {
    title: "ডাবল বটম",
    what: "তুলনীয় দুটি তলদেশ, মাঝে একটি অর্থপূর্ণ বাউন্সসহ — দাম একই ফ্লোর দুইবার পরীক্ষা করেছে এবং দুইবারই টিকেছে। ডাবল টপের বিপরীত।",
    use: "ক্লাসিক বুলিশ-রিভার্সাল পাঠ: একই ফ্লোর দুইবার ধরে রাখাকে দুর্বল হয়ে আসা বিক্রয়চাপ হিসেবে পড়া হয়। 'নেকলাইন' (দুই তলদেশের মাঝের হাই) হলো সেই লেভেল যা কিছু ট্রেডার নিশ্চিতকরণ ব্রেকের জন্য দেখেন।",
    watch: "একই সতর্কতা, বিপরীতভাবে: দুটি তলদেশ একটি ডাউনট্রেন্ডে স্বাভাবিক শব্দ হতে পারে, আর এটি DSE ডেটায় কিছু পূর্বাভাস দেয় বলে প্রমাণিত নয়।",
    example: "একটি শেয়ার ৳১০০-এ নেমে, ৳১২০-এ বাউন্স করে, আবার ৳৯৯-এ নেমে, তারপর উঠছে — পরে ৳১২০ (নেকলাইন) এর উপরে ক্লোজ করলে এই প্যাটার্ন তাকে 'ব্রেকআউট' বলে।",
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
  institutional_selling: "smartmoney",
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
  sponsor_selling: { t: "স্পনসরদের বিক্রি", d: "অভ্যন্তরীণরা নিজেদের অংশ কমিয়েছেন" },
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
  dividend_yield: { t: "সর্বোচ্চ নগদ লভ্যাংশ", d: "সর্বশেষ ঘোষিত নগদ লভ্যাংশ ÷ আজকের দাম (অতীত, পূর্বাভাস নয়)" },
  foreign_buying: { t: "বিদেশি", d: "বিদেশি বিনিয়োগকারীরা শেষ প্রকাশে অংশ পরিবর্তন করেছে" },
  institutional_buying: { t: "প্রতিষ্ঠান", d: "প্রতিষ্ঠান শেষ প্রকাশে অংশ পরিবর্তন করেছে" },
  institutional_selling: { t: "প্রাতিষ্ঠানিক বিক্রি", d: "প্রতিষ্ঠান শেষ প্রকাশে অংশ কমিয়েছে" },
  most_watched: { t: "সর্বাধিক ওয়াচড", d: "যাদের সবচেয়ে বেশি ওয়াচ করা হচ্ছে" },
  most_discussed: { t: "সর্বাধিক আলোচিত", d: "যাদের নিয়ে সবচেয়ে বেশি আলোচনা" },
  attention_rising: { t: "আলোচনা বাড়ছে", d: "স্বাভাবিকের চেয়ে অনেক বেশি আলোচনা" },
  chart_patterns: { t: "চার্ট প্যাটার্ন", d: "নিশ্চিত সুইং থেকে তৈরি ক্লাসিক চার্ট আকার (ত্রিভুজ, চ্যানেল, ডাবল টপ/বটম)" },
};
