import type {
  ResearchChartCondition,
  ResearchChartConditionCheck,
  ResearchConditionKey,
  ResearchConditionState,
} from "./api";

export type ResearchChartLang = "en" | "bn";

const COPY = {
  en: {
    title: "Research chart",
    layers: "Research layers",
    dataThrough: "Conditions through",
    completedClose: "completed close",
    currentPriceNote: "Price may include the current delayed session.",
    calculations: "Calculation details",
    actual: "Actual",
    threshold: "Required",
    why: "Why it matters",
    limitation: "Limitation",
    history: "Previous observations",
    noHistory: "No earlier observation in the available history",
    profile: "Volume profile",
    profileUnavailable:
      "Not shown: verified intraday volume-at-price coverage is unavailable. Daily candles are not used to fabricate a profile.",
    unavailable: "Research layers are temporarily unavailable; the price chart remains usable.",
    disclaimer:
      "Completed-session research only. An observed condition is not a recommendation, probability estimate, target, or order.",
    states: {
      observed: "Observed",
      not_observed: "Not observed",
      unavailable: "Data unavailable",
    },
    checks: { passed: "Met", failed: "Not met", unavailable: "No data" },
  },
  bn: {
    title: "রিসার্চ চার্ট",
    layers: "গবেষণার স্তর",
    dataThrough: "শর্তের তথ্য",
    completedClose: "সমাপ্ত সেশনের ক্লোজ পর্যন্ত",
    currentPriceNote: "দামে চলতি বিলম্বিত সেশনের তথ্য থাকতে পারে।",
    calculations: "হিসাবের বিস্তারিত",
    actual: "প্রকৃত মান",
    threshold: "প্রয়োজন",
    why: "কেন গুরুত্বপূর্ণ",
    limitation: "সীমাবদ্ধতা",
    history: "আগের পর্যবেক্ষণ",
    noHistory: "পাওয়া ইতিহাসে আগের কোনো পর্যবেক্ষণ নেই",
    profile: "দামভিত্তিক ভলিউম প্রোফাইল",
    profileUnavailable:
      "দেখানো হয়নি: নির্ভরযোগ্য ইন্ট্রাডে দাম-ভলিউম তথ্য নেই। দৈনিক ক্যান্ডেল থেকে কৃত্রিম প্রোফাইল বানানো হয় না।",
    unavailable: "গবেষণার স্তর এখন পাওয়া যাচ্ছে না; দামের চার্ট ব্যবহার করা যাবে।",
    disclaimer:
      "শুধু সমাপ্ত সেশনের গবেষণা। শর্ত মেলা কোনো পরামর্শ, সম্ভাবনার হিসাব, লক্ষ্য বা অর্ডার নয়।",
    states: {
      observed: "শর্ত মিলেছে",
      not_observed: "এখন মেলেনি",
      unavailable: "তথ্য পাওয়া যায়নি",
    },
    checks: { passed: "মিলেছে", failed: "মেলেনি", unavailable: "তথ্য নেই" },
  },
} as const;

const CONDITION_BN: Record<
  ResearchConditionKey,
  { title: string; why: string; limitation: string }
> = {
  trend_alignment: {
    title: "ট্রেন্ডের সামঞ্জস্য",
    why: "২০ সেশনের গড় ৫০ সেশনের গড়ের ওপরে থেকে দুটিই বাড়লে এক দিনের লাফের বদলে ধারাবাহিক দিক বোঝা যায়।",
    limitation: "মুভিং অ্যাভারেজ দামের পরে প্রতিক্রিয়া জানায়। এটি মুভের শেষ দিকেও থাকতে পারে এবং ভবিষ্যৎ রিটার্ন বলে না।",
  },
  participation_expansion: {
    title: "ভলিউম অংশগ্রহণ",
    why: "দামের শক্তির সঙ্গে আগের ২০ সেশনের তুলনায় বেশি ভলিউম থাকলে শুধু দাম বাড়ার চেয়ে বিস্তৃত অংশগ্রহণ বোঝায়।",
    limitation: "বড় ভলিউম বিক্রি, সংবাদ বা পুনর্বিন্যাস থেকেও আসতে পারে। এটি কোনো প্রতিষ্ঠান বা সঞ্চয় নিশ্চিত করে না।",
  },
  controlled_pullback_context: {
    title: "নিয়ন্ত্রিত পুলব্যাক",
    why: "বড় ট্রেন্ড অক্ষুণ্ণ রেখে কম ভলিউমে দাম ২০ সেশনের গড়ের কাছে ফিরলে সুশৃঙ্খল বিরতি নিয়ে আরও গবেষণা করা যায়।",
    limitation: "এটি দৈনিক বারের প্রেক্ষাপট; ইন্ট্রাডে এন্ট্রি বা ট্রেডিং কৌশল নয়। আলাদা ঝুঁকি ও তারল্য যাচাই দরকার।",
  },
};

const CHECK_LABEL_BN: Record<string, string> = {
  "Close above EMA20": "ক্লোজ EMA20-এর ওপরে",
  "EMA20 above EMA50": "EMA20, EMA50-এর ওপরে",
  "EMA20 rising over 5 sessions": "৫ সেশনে EMA20 বাড়ছে",
  "EMA50 rising over 10 sessions": "১০ সেশনে EMA50 বাড়ছে",
  "Volume versus prior 20 sessions": "আগের ২০ সেশনের তুলনায় ভলিউম",
  "Completed-session price change": "সমাপ্ত সেশনের দাম পরিবর্তন",
  "Close relative to EMA20": "EMA20-এর তুলনায় ক্লোজ",
  "Close near EMA20": "ক্লোজ EMA20-এর কাছে",
  "Close above EMA50": "ক্লোজ EMA50-এর ওপরে",
  "Volume remains controlled": "ভলিউম নিয়ন্ত্রিত আছে",
};

export function researchChartCopy(lang: ResearchChartLang) {
  return COPY[lang];
}

export function conditionText(condition: ResearchChartCondition, lang: ResearchChartLang) {
  if (lang === "en") {
    return {
      title: condition.title,
      why: condition.why_it_matters,
      limitation: condition.limitation,
    };
  }
  return CONDITION_BN[condition.key];
}

export function conditionStateLabel(state: ResearchConditionState, lang: ResearchChartLang) {
  return COPY[lang].states[state];
}

export function conditionSummary(condition: ResearchChartCondition, lang: ResearchChartLang) {
  const available = condition.checks.filter((check) => check.passed !== null).length;
  const passed = condition.checks.filter((check) => check.passed === true).length;
  const total = condition.checks.length;
  if (lang === "bn") {
    if (condition.state === "unavailable") return `${total}টির মধ্যে ${available}টি যাচাই করা গেছে।`;
    if (condition.state === "observed") return `${total}টি সমাপ্ত-সেশন যাচাইয়ের সবগুলো মিলেছে।`;
    return `${total}টির মধ্যে ${passed}টি মিলেছে; সম্পূর্ণ শর্ত এখনো মেলেনি।`;
  }
  if (condition.state === "unavailable") return `${available} of ${total} checks have enough data.`;
  if (condition.state === "observed") return `All ${total} completed-session checks are present.`;
  return `${passed} of ${total} checks are present; the full condition is not observed.`;
}

export function checkLabel(check: ResearchChartConditionCheck, lang: ResearchChartLang) {
  return lang === "bn" ? (CHECK_LABEL_BN[check.label] ?? check.fact_key) : check.label;
}

export function formatCheckValue(check: ResearchChartConditionCheck) {
  if (check.observed === null) return "—";
  const sign = check.observed > 0 ? "+" : "";
  if (check.unit === "multiple") return `${check.observed.toFixed(2)}x`;
  return `${sign}${check.observed.toFixed(1)}%`;
}

export function checkStateLabel(check: ResearchChartConditionCheck, lang: ResearchChartLang) {
  if (check.passed === null) return COPY[lang].checks.unavailable;
  return check.passed ? COPY[lang].checks.passed : COPY[lang].checks.failed;
}

export function recentTransitions(condition: ResearchChartCondition, limit = 6) {
  return condition.transitions.slice(-Math.max(0, limit));
}
