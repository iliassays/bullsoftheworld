import { useEffect, useState, type ReactNode } from "react";
import { CompanyLogo } from "../components/CompanyLogo";
import { EvidenceChip, evidenceExplain } from "../components/EvidenceChip";
import { FreshnessTag } from "../components/FreshnessTag";
import { Link } from "react-router-dom";
import { Empty, Pct, Spinner, taka } from "../components/ui";
import { api, type ScannerResponse, type Screen, type ScreenItem } from "../lib/api";
import { useAuth } from "../lib/auth";
import { type Lang, useLang } from "../lib/i18n";
import { Watchlist } from "./Watchlist";

type Tab = "today" | "value" | "lens" | "watchlist";
type Picked = { board: Screen; item: ScreenItem };

const BOARD_ICON: Record<string, string> = {
  quality_reversal: "🌊",
  oversold_quality: "🧲",
  active_today: "🔥",
  most_active: "💸",
  value_quality: "⭐",
  dividend_quality: "💵",
  lens_agreement: "🧭",
  lens_buffett_quality: "🏛️",
  lens_graham_value: "🧮",
  lens_smart_money: "🏦",
  lens_risk_control: "🛡️",
};

const BOARD_TEXT: Record<string, Record<Lang, { title: string; desc: string; label: string }>> = {
  quality_reversal: {
    en: {
      title: "Beaten-Down, Profitable",
      desc: "Deeply below their 52-week high but still profitable — and just crossed back above their recent 5-day high.",
      label: "Broke 5-day high",
    },
    bn: {
      title: "অনেক পড়েছে, তবু লাভজনক",
      desc: "৫২-সপ্তাহের উচ্চতা থেকে অনেক নিচে, কিন্তু লাভজনক — এবং সদ্য নিজের ৫ দিনের উচ্চতা ছাড়িয়ে গেছে।",
      label: "৫ দিনের high ভাঙল",
    },
  },
  oversold_quality: {
    en: {
      title: "Oversold Quality",
      desc: "Profitable, liquid names deep in the oversold zone — a zone to research, not a timing call.",
      label: "RSI oversold",
    },
    bn: {
      title: "ওভারসোল্ড কোয়ালিটি",
      desc: "লাভজনক, লিকুইড শেয়ার যেগুলোর RSI ওভারসোল্ড জোনে — গবেষণার জায়গা, টাইমিং সিগন্যাল নয়।",
      label: "RSI ওভারসোল্ড",
    },
  },
  active_today: {
    en: {
      title: "Unusual Activity",
      desc: "Liquid names where volume and turnover are above their own normal pace.",
      label: "Unusual activity",
    },
    bn: {
      title: "অস্বাভাবিক লেনদেন",
      desc: "লিকুইড শেয়ার যেখানে নিজের স্বাভাবিক গতির তুলনায় আজ ভলিউম/টার্নওভার বেশি।",
      label: "অস্বাভাবিক লেনদেন",
    },
  },
  most_active: {
    en: {
      title: "Top Turnover",
      desc: "Where the most traded value is today, liquidity-gated.",
      label: "High turnover",
    },
    bn: {
      title: "আজ বেশি টাকার লেনদেন",
      desc: "আজ কোথায় বেশি টাকা ঘুরছে, লিকুইডিটি ফিল্টারসহ।",
      label: "বেশি টার্নওভার",
    },
  },
  value_quality: {
    en: {
      title: "Value + Profitability",
      desc: "Cheaper than sector peers, but only when profitability support is present.",
      label: "Value + quality",
    },
    bn: {
      title: "ভ্যালু + লাভজনকতা",
      desc: "খাতের তুলনায় সস্তা, তবে সাথে লাভজনকতার সমর্থন থাকতে হবে।",
      label: "ভ্যালু + মান",
    },
  },
  dividend_quality: {
    en: {
      title: "Dividend Quality",
      desc: "Cash-yield names with positive earnings context.",
      label: "Dividend check",
    },
    bn: {
      title: "লভ্যাংশ + কভারেজ",
      desc: "নগদ লভ্যাংশের সাথে আয়ের কভারেজ আছে কি না দেখার তালিকা।",
      label: "লভ্যাংশ চেক",
    },
  },
  lens_agreement: {
    en: {
      title: "Multi-Lens Agreement",
      desc: "At least 3 of 5 lenses are supportive, while risk-control is not caution.",
      label: "Lens agreement",
    },
    bn: {
      title: "মাল্টি-লেন্স এগ্রিমেন্ট",
      desc: "৫টির মধ্যে অন্তত ৩টি লেন্স সহায়ক, এবং risk-control caution নয়।",
      label: "লেন্স এগ্রিমেন্ট",
    },
  },
  lens_buffett_quality: {
    en: {
      title: "Quality Lens",
      desc: "Buffett/Munger-style screen: stronger profitability, positive earnings context and enough liquidity to study.",
      label: "Quality pass",
    },
    bn: {
      title: "কোয়ালিটি লেন্স",
      desc: "Buffett/Munger-style স্ক্রিন: শক্ত লাভজনকতা, আয়ের সমর্থন এবং গবেষণার মতো লিকুইডিটি।",
      label: "কোয়ালিটি পাস",
    },
  },
  lens_graham_value: {
    en: {
      title: "Graham Value Lens",
      desc: "Margin-of-safety screen: cheaper than sector peers with positive earnings and basic profitability support.",
      label: "Value pass",
    },
    bn: {
      title: "Graham ভ্যালু লেন্স",
      desc: "Margin-of-safety স্ক্রিন: খাতের তুলনায় সস্তা, সাথে পজিটিভ আয় ও লাভজনকতার সমর্থন।",
      label: "ভ্যালু পাস",
    },
  },
  lens_smart_money: {
    en: {
      title: "Smart Money Lens",
      desc: "Disclosed institutional/foreign accumulation with liquidity context.",
      label: "Flow pass",
    },
    bn: {
      title: "স্মার্ট মানি লেন্স",
      desc: "প্রতিষ্ঠান/বিদেশি মালিকানার প্রকাশিত বৃদ্ধি, সাথে লিকুইডিটির প্রেক্ষাপট।",
      label: "ফ্লো পাস",
    },
  },
  lens_risk_control: {
    en: {
      title: "Risk-Controlled Lens",
      desc: "Better tradability: liquidity, free-float support and lower fragility. This is not an upside screen.",
      label: "Tradable",
    },
    bn: {
      title: "রিস্ক-কন্ট্রোল লেন্স",
      desc: "ভালোভাবে লেনদেন করা যায় কি না: লিকুইডিটি, free-float ও কম fragility। এটি upside screen নয়।",
      label: "লেনদেনযোগ্য",
    },
  },
};

function boardText(board: Screen, lang: Lang) {
  return BOARD_TEXT[board.key]?.[lang] ?? { title: board.title, desc: board.description, label: board.title };
}

function metricText(board: Screen, item: ScreenItem, lang: Lang): string {
  if (board.key === "most_active") return lang === "bn" ? `৳${item.value.toFixed(1)}cr` : `Tk ${item.value.toFixed(1)}cr`;
  if (board.value_label === "RSI") return `RSI ${item.value.toFixed(0)}`;
  if (board.value_label === "yield") return `${item.value.toFixed(1)}%`;
  if (board.value_label === "x sector") return `${item.value.toFixed(2)}x`;
  if (board.value_label === "score") return `${item.value.toFixed(0)}/10`;
  if (board.value_label === "lenses") return `${item.value.toFixed(0)}/5`;
  if (board.value_label.includes("%")) return `${item.value.toFixed(0)}%`;
  if (board.value_label === "activity") return lang === "bn" ? "সক্রিয়" : "Active";
  return item.value.toFixed(1);
}

function liquidityText(item: ScreenItem, lang: Lang): string | null {
  if (!item.liquidity) return null;
  if (lang === "bn") {
    if (item.liquidity.includes("Deep")) return "গভীর লিকুইডিটি";
    if (item.liquidity.includes("Tradeable")) return "লেনদেনযোগ্য";
    if (item.liquidity.includes("Watch")) return "অর্ডার সাইজে সতর্কতা";
    if (item.liquidity.includes("Thin")) return "পাতলা লিকুইডিটি";
    if (item.liquidity.includes("Z")) return "Z ঝুঁকি";
  }
  return item.liquidity;
}

function defaultRisk(board: Screen, lang: Lang): string {
  if (lang === "bn") {
    if (board.key === "lens_agreement") return "Agreement strong হলেও এটি recommendation নয়। নতুন খবর, দাম বেশি হয়ে যাওয়া, বা হঠাৎ liquidity change আলাদা ঝুঁকি।";
    if (board.key === "lens_buffett_quality") return "ভালো কোম্পানিও দামে বেশি হলে রিটার্ন খারাপ হতে পারে। one-off EPS বা অতিরিক্ত ঋণ দেখুন।";
    if (board.key === "lens_graham_value") return "সস্তা শেয়ার value trap হতে পারে, বিশেষ করে EPS কমছে বা governance/news দুর্বল হলে।";
    if (board.key === "lens_smart_money") return "Disclosure delayed; বড় investor-রাও ভুল করতে পারে বা পরে বিক্রি করতে পারে।";
    if (board.key === "lens_risk_control") return "লিকুইড নামেও gap, circuit বা ভুল order size ক্ষতি করতে পারে।";
    if (board.key === "value_quality") return "সস্তা মানেই ভালো নয়; দুর্বল ব্যবসা হলে value trap হতে পারে।";
    if (board.key === "dividend_quality") return "অতীত লভ্যাংশ ভবিষ্যৎ লভ্যাংশের নিশ্চয়তা নয়।";
    if (board.key === "oversold_quality") return "ওভারসোল্ড আরও ওভারসোল্ড হতে পারে; সত্যিকারের ব্যবসায়িক সমস্যা থাকলে কম দামই প্রাপ্য। এটি buy signal নয়।";
    if (board.key === "active_today" || board.key === "most_active") return "অ্যাক্টিভ মানেই দাম বাড়বে নয়; heavy selling-ও হতে পারে।";
    return "অনেক পড়া শেয়ার আরও পড়তে পারে; বিস্তৃত ডাউনট্রেন্ডে এই প্যাটার্ন প্রায়ই falling knife, তলদেশ নয়। এটি buy signal নয়।";
  }
  if (board.key === "oversold_quality") return "Oversold can stay oversold, and a genuine business problem deserves a low price. This is a research zone, not a buy signal.";
  if (board.key === "lens_agreement") return "Agreement is not a recommendation. New news, valuation stretch, and sudden liquidity changes can still break the setup.";
  if (board.key === "lens_buffett_quality") return "A good business can still be a poor trade if price is stretched. Check one-off EPS, debt and valuation.";
  if (board.key === "lens_graham_value") return "Cheap can be a value trap, especially if EPS is falling or governance/news is weak.";
  if (board.key === "lens_smart_money") return "Disclosure is delayed; large investors can also be early, wrong, or sellers later.";
  if (board.key === "lens_risk_control") return "Liquid names can still gap, hit circuit limits, or hurt if order size is too large.";
  if (board.key === "value_quality") return "Cheap can still be a value trap if earnings weaken.";
  if (board.key === "dividend_quality") return "Past dividend does not guarantee future dividend.";
  if (board.key === "active_today" || board.key === "most_active") return "Active does not mean bullish; heavy selling can also create activity.";
  return "Deeply fallen stocks can keep falling — in a broad downtrend this pattern is often a falling knife, not a bottom. This is not a buy signal.";
}

function checksFor(board: Screen, item: ScreenItem, lang: Lang): string[] {
  if (lang === "en" && item.check_next?.length) return item.check_next;
  if (lang === "bn") {
    if (board.key === "lens_agreement") return ["লেন্স comparison", "খবর", "ADTV/order size", "মূল লেভেল"];
    if (board.key === "lens_buffett_quality") return ["৫ বছরের EPS", "ঋণ/NAV", "ডিভিডেন্ড", "valuation"];
    if (board.key === "lens_graham_value") return ["EPS ট্রেন্ড", "ঋণ/NAV", "খবর", "সেক্টর P/E"];
    if (board.key === "lens_smart_money") return ["Disclosure date", "CMF/OBV", "দামের reaction", "ভলিউম"];
    if (board.key === "oversold_quality") return ["কেন পড়ল (খবর)", "EPS ট্রেন্ড", "সাপোর্ট লেভেল", "অর্ডার সাইজ"];
    if (board.key === "lens_risk_control") return ["ADTV/order size", "bid-ask spread", "ভোলাটিলিটি", "সাপোর্ট"];
    if (board.key === "value_quality") return ["EPS ট্রেন্ড", "ঋণ/NAV", "খবর", "সেক্টর তুলনা"];
    if (board.key === "dividend_quality") return ["রেকর্ড ডেট", "EPS কভার", "পেআউট ইতিহাস", "দাম সমন্বয়"];
    if (board.key === "active_today" || board.key === "most_active") return ["খবর", "দামের দিক", "ADTV", "খাত"];
    return ["খবর", "ভলিউম", "সাপোর্ট", "অর্ডার সাইজ"];
  }
  if (board.key === "lens_agreement") return ["Lens comparison", "News", "ADTV/order size", "Key levels"];
  if (board.key === "lens_buffett_quality") return ["5Y EPS", "Debt/NAV", "Dividend history", "Valuation"];
  if (board.key === "lens_graham_value") return ["EPS trend", "Debt/NAV", "News", "Sector P/E"];
  if (board.key === "lens_smart_money") return ["Disclosure date", "CMF/OBV", "Price reaction", "Volume"];
  if (board.key === "lens_risk_control") return ["ADTV/order size", "Bid-ask spread", "Volatility", "Support"];
  if (board.key === "value_quality") return ["EPS trend", "Debt/NAV", "News", "Sector compare"];
  if (board.key === "dividend_quality") return ["Record date", "EPS cover", "Payout history", "Price adjustment"];
  if (board.key === "active_today" || board.key === "most_active") return ["News", "Price direction", "ADTV", "Sector"];
  return ["News", "Volume", "Support", "Order size"];
}

function scannerWhy(board: Screen, item: ScreenItem, lang: Lang, fallback: string): string {
  if (lang === "bn") {
    if (board.key === "quality_reversal") {
      return `৫২-সপ্তাহের উচ্চতা থেকে প্রায় ${Math.abs(item.value).toFixed(0)}% নিচে, তবু লাভজনক এবং সদ্য নিজের ৫ দিনের উচ্চতা ছাড়িয়ে গেছে।`;
    }
    if (board.key === "oversold_quality") {
      return `RSI ${item.value.toFixed(0)} — ঐতিহাসিকভাবে DSE-তে এই জোন থেকেই recovery এসেছে — এবং ব্যবসাটি এখনো লাভজনক (${item.note ?? ""})।`;
    }
    if (board.key === "active_today") {
      return item.note === "heating_up"
        ? "নিজের স্বাভাবিক গতির তুলনায় আজ ভলিউম ও টার্নওভার দুটোই বেশি।"
        : "নিজের স্বাভাবিক লেনদেনের তুলনায় আজ লেনদেনের চাপ বেশি।";
    }
    if (board.key === "value_quality") {
      return `খাতের তুলনায় P/E কম (${item.value.toFixed(2)}x), সাথে লাভজনকতার সমর্থন আছে।`;
    }
    if (board.key === "dividend_quality") {
      return `নগদ লভ্যাংশের ইয়িল্ড ${item.value.toFixed(1)}%, এবং EPS পজিটিভ।`;
    }
    if (board.key === "most_active") {
      return "আজ টাকার লেনদেন বেশি; দামের দিক ও কারণ আলাদা করে যাচাই করুন।";
    }
    if (board.key === "lens_agreement") {
      return `${item.value.toFixed(0)}/5 lens সহায়ক। ${item.note || "Quality, Value, Technical, Smart Money ও Risk একসাথে পড়ুন।"}`;
    }
    if (board.key === "lens_buffett_quality") {
      return `কোয়ালিটি স্কোর ${item.value.toFixed(0)}/10। ${item.note || "লাভজনকতা ও আয়ের প্রেক্ষাপট স্ক্রিনকে সমর্থন করছে।"}`;
    }
    if (board.key === "lens_graham_value") {
      return `ভ্যালু স্কোর ${item.value.toFixed(0)}/10। ${item.note || "valuation খাতের তুলনায় কম এবং আয়ের সমর্থন আছে।"}`;
    }
    if (board.key === "lens_smart_money") {
      return `ownership-flow স্কোর ${item.value.toFixed(0)}/10। ${item.note || "প্রকাশিত মালিকানায় সহায়ক পরিবর্তন দেখা যাচ্ছে।"}`;
    }
    if (board.key === "lens_risk_control") {
      return `risk-control স্কোর ${item.value.toFixed(0)}/10। ${item.note || "লিকুইডিটি ও fragility ফিল্টার তুলনামূলক পরিষ্কার।"}`;
    }
  }
  return item.why || fallback;
}

function ScannerSheet({ picked, onClose }: { picked: Picked; onClose: () => void }) {
  const { lang } = useLang();
  const { board, item } = picked;
  const text = boardText(board, lang);
  const checks = checksFor(board, item, lang);
  const risk = lang === "bn" ? defaultRisk(board, lang) : item.risk_note || defaultRisk(board, lang);
  const why = scannerWhy(board, item, lang, text.desc);

  // One compact liquidity line: ADTV + the order-size guide (5% of ADTV, from the API).
  const liqParts: string[] = [];
  if (item.adtv_mn != null) liqParts.push(`ADTV ৳${item.adtv_mn.toFixed(1)}mn`);
  if (item.safe_order_mn != null)
    liqParts.push(
      lang === "bn"
        ? `নিরাপদ অর্ডার ≤ ৳${item.safe_order_mn.toFixed(1)}mn`
        : `safe order ≤ ৳${item.safe_order_mn.toFixed(1)}mn`,
    );
  if (item.turnover_mn != null)
    liqParts.push(lang === "bn" ? `আজ ৳${item.turnover_mn.toFixed(1)}mn` : `today ৳${item.turnover_mn.toFixed(1)}mn`);

  const Row = ({ label, children }: { label: string; children: ReactNode }) => (
    <div className="flex items-baseline justify-between gap-4 border-b border-dashed border-border/70 py-2.5 text-[12.5px] last:border-b-0">
      <span className="shrink-0 text-muted">{label}</span>
      <span className="min-w-0 text-right leading-snug text-text/90">{children}</span>
    </div>
  );

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/55" onClick={onClose}>
      <div
        className="w-full max-w-md max-h-[86vh] overflow-y-auto rounded-t-2xl border border-accent/30 bg-surface p-4 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mx-auto mb-3 h-1 w-9 rounded-full bg-border" />
        <div className="flex items-center gap-2.5">
          <CompanyLogo code={item.code} size={34} />
          <div className="min-w-0">
            <div className="truncate text-base font-extrabold">
              ${item.code} · {lang === "bn" ? "কেন মিলেছে" : "why it matched"}
            </div>
            <div className="text-[11px] text-muted tnum">
              {item.last_close > 0 ? taka(item.last_close) : ""}
              {item.change_1d != null && (
                <>
                  {" "}
                  · <Pct value={item.change_1d} />
                </>
              )}
              {item.category ? ` · Cat ${item.category}` : ""}
            </div>
          </div>
          <button onClick={onClose} className="ml-auto shrink-0 px-2 text-sm text-muted" aria-label="close">
            ✕
          </button>
        </div>

        {/* The readable sentence first — everything else is supporting detail. */}
        <p lang={lang} className="mt-3 text-[14px] leading-relaxed text-text">
          {why}
        </p>

        <div className="mt-2">
          <Row label={lang === "bn" ? "এরপর যাচাই" : "Verify next"}>{checks.join(" · ")}</Row>
          {liqParts.length > 0 && (
            <Row label={lang === "bn" ? "লিকুইডিটি" : "Liquidity"}>{liqParts.join(" — ")}</Row>
          )}
          <Row label={lang === "bn" ? "ঝুঁকি" : "Risk"}>{risk}</Row>
        </div>

        <Link
          to={`/s/${item.code}`}
          className="mt-4 block rounded-xl bg-accent py-3 text-center text-sm font-extrabold text-bg"
        >
          {lang === "bn" ? `আগে $${item.code} নিজে যাচাই করুন →` : `Research $${item.code} before acting →`}
        </Link>
      </div>
    </div>
  );
}


function ScannerRow({ board, item, onPick }: { board: Screen; item: ScreenItem; onPick: () => void }) {
  const { lang } = useLang();
  const text = boardText(board, lang);
  const why = scannerWhy(board, item, lang, text.desc);
  // Per-row noise cut: the board header already names the setup, so no per-row label chip.
  // Liquidity only appears when it's a warning — deep/tradeable is the expected default.
  const liq = liquidityText(item, lang);
  const liqWarning =
    liq && item.liquidity && !item.liquidity.includes("Deep") && !item.liquidity.includes("Tradeable");
  return (
    <button onClick={onPick} className="flex w-full items-center gap-3 py-3 text-left">
      <CompanyLogo code={item.code} size={28} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-extrabold text-sm">${item.code}</span>
          {liqWarning && (
            <span className="rounded-full border border-down/40 bg-down/10 px-2 py-0.5 text-[9px] font-semibold text-down">
              {liq}
            </span>
          )}
        </div>
        <div className="mt-0.5 line-clamp-1 text-[11px] leading-snug text-muted">{why}</div>
      </div>
      <div className="shrink-0 text-right tnum">
        {item.last_close > 0 && <div className="text-[13px] font-semibold">{taka(item.last_close)}</div>}
        <div className="text-xs font-semibold">
          {item.change_1d != null ? <Pct value={item.change_1d} /> : <span className="text-muted">{metricText(board, item, lang)}</span>}
        </div>
      </div>
    </button>
  );
}

// The regime-dependent boards get a louder, live caution when DSEX sits below its 200-day
// average — the research says the reversal edge was proven in a *recovering* market only.
const REGIME_SENSITIVE = new Set(["quality_reversal", "oversold_quality"]);

function RegimeBanner() {
  const { lang } = useLang();
  return (
    <div className="mt-2 rounded-xl border border-down/40 bg-down/10 p-2.5 text-[11px] leading-snug text-down">
      {lang === "bn"
        ? "⚠️ বাজার এখন ২০০-দিনের গড়ের নিচে। এই প্যাটার্নের এজ রিকভারি মার্কেটে প্রমাণিত — ডাউনট্রেন্ডে গভীর পতন আরও পড়তে পারে।"
        : "⚠️ The market is below its 200-day average. This pattern's edge was proven in a recovering market — in a downtrend, deep falls can keep falling."}
    </div>
  );
}

function BoardCard({
  board,
  regime,
  onPick,
}: {
  board: Screen;
  regime?: string | null;
  onPick: (picked: Picked) => void;
}) {
  const { lang } = useLang();
  const text = boardText(board, lang);
  const [explain, setExplain] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const visible = showAll ? board.items : board.items.slice(0, 5);

  // A silent board is discipline, not content — it costs one slim line, not a card.
  // (Quality Reversal fires ~50x/year across the whole market by design; most days: nothing.)
  if (board.items.length === 0) {
    return (
      <section className="flex items-center gap-2 rounded-2xl border border-border/60 bg-surface/50 px-4 py-2.5">
        <span className="text-sm opacity-60">{BOARD_ICON[board.key] ?? "📈"}</span>
        <span className="min-w-0 truncate text-[10px] font-bold uppercase tracking-[0.12em] text-muted">
          {text.title}
        </span>
        <span className="ml-auto shrink-0 text-[11px] text-muted">
          {lang === "bn" ? "আজ কোনো ম্যাচ নেই — এটাও তথ্য" : "no match today — that's data too"}
        </span>
      </section>
    );
  }

  return (
    <section className="rounded-2xl border border-border bg-surface p-4">
      <div className="flex items-center gap-2">
        <span className="text-base">{BOARD_ICON[board.key] ?? "📈"}</span>
        <span className="min-w-0 truncate text-[11px] font-bold uppercase tracking-[0.12em] text-text/90">
          {text.title}
        </span>
        <EvidenceChip evidence={board.evidence} onToggle={() => setExplain((v) => !v)} />
        <span className="ml-auto shrink-0 text-[11px] font-semibold text-accent tnum">
          {board.items.length} {lang === "bn" ? "টি ম্যাচ" : "matches"}
        </span>
      </div>
      {explain && board.evidence && (
        <p lang={lang} className="mt-2 rounded-xl bg-card/60 border border-border p-2.5 text-[11px] leading-relaxed text-muted">
          {evidenceExplain(board.evidence, lang)}
        </p>
      )}
      {REGIME_SENSITIVE.has(board.key) && regime === "below_200dma" && <RegimeBanner />}
      <div className="mt-1 flex flex-col divide-y divide-border">
        {visible.map((item) => (
          <ScannerRow key={item.code} board={board} item={item} onPick={() => onPick({ board, item })} />
        ))}
      </div>
      {!showAll && board.items.length > 5 && (
        <button
          onClick={() => setShowAll(true)}
          className="mt-1 block w-full border-t border-border/60 pt-2 text-center text-[11px] font-semibold text-accent"
        >
          {lang === "bn" ? "আরও দেখুন" : "View more"} ({board.items.length - 5})
        </button>
      )}
    </section>
  );
}

function ScannerGuide() {
  const { lang } = useLang();
  const useSteps =
    lang === "bn"
      ? [
          "প্রথমে সেটআপ বেছে নিন: আজকের activity, turnaround, value, dividend বা Investor Lens.",
          "যে শেয়ার দেখাবে, সেটি buy/sell signal নয়। সারি চাপুন এবং কেন এসেছে, ঝুঁকি, ADTV/order guide দেখুন।",
          "তারপর পুরো স্টক পেজে চার্ট, খবর, ফান্ডামেন্টাল, সাপোর্ট/রেজিস্ট্যান্স ও নিজের risk limit মিলিয়ে সিদ্ধান্ত নিন।",
        ]
      : [
          "Start with the setup: today's activity, turnaround, value, dividend, or Investor Lens.",
          "A match is not a buy/sell signal. Tap the row and check why it appeared, risk, ADTV and order guide.",
          "Then open the stock page to review chart, news, fundamentals, levels and your own risk limit.",
        ];
  const generated =
    lang === "bn"
      ? [
          "Turnaround: ৫২-সপ্তাহের high থেকে অনেক নিচে, কিন্তু লাভজনক, P/E reasonable, liquid, এবং সাম্প্রতিক ৫ দিনের high ভাঙছে।",
          "Unusual Activity: নিজের স্বাভাবিক ভলিউম/টার্নওভারের তুলনায় আজ activity বেশি; thin/Z category বাদ দেওয়া হয়।",
          "Value + Dividend: খাতের তুলনায় valuation, profitability, cash dividend, positive EPS এবং liquidity একসাথে দেখা হয়।",
          "Investor Lens: Multi-Lens Agreement আগে দেখায়, তারপর Quality, Value, Smart Money ও Risk-Controlled আলাদা board দেখায়।",
        ]
      : [
          "Turnaround: far below 52-week high, still profitable, reasonable P/E, liquid, and breaking the recent 5-day high.",
          "Unusual Activity: volume/turnover is high versus the stock's own normal pace; thin/Z-category names are filtered out.",
          "Value + Dividend: combines sector valuation, profitability, cash dividend, positive EPS and liquidity checks.",
          "Investor Lens: starts with Multi-Lens Agreement, then shows separate Quality, Value, Smart Money and Risk-Controlled boards.",
        ];
  return (
    <section className="rounded-2xl border border-border bg-surface p-4">
      <div className="text-sm font-bold">
        {lang === "bn" ? "স্ক্যানার কীভাবে ব্যবহার করবেন" : "How to use this scanner"}
      </div>
      <p className="mt-1 text-xs leading-relaxed text-muted">
        {lang === "bn"
          ? "এটি টিপস পেজ নয়। এটি ডেটা দিয়ে ছোট shortlist বানায়, যাতে আপনি দ্রুত বুঝতে পারেন কোন শেয়ার আরও গবেষণার যোগ্য।"
          : "This is not a tips page. It creates a small data-backed shortlist so you can decide what deserves deeper research."}
      </p>

      <div className="mt-3 grid gap-2">
        {useSteps.map((step, idx) => (
          <div key={step} className="flex gap-2 rounded-xl border border-border bg-card/50 p-2.5">
            <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent/15 text-[11px] font-bold text-accent">
              {idx + 1}
            </div>
            <p className="text-[12px] leading-relaxed text-text/90">{step}</p>
          </div>
        ))}
      </div>

      <details className="mt-3 rounded-xl border border-border bg-card/40 p-3">
        <summary className="cursor-pointer text-xs font-bold text-accent">
          {lang === "bn" ? "এই তালিকাগুলো কীভাবে তৈরি হয়" : "How these lists are generated"}
        </summary>
        <div className="mt-2 flex flex-col gap-2">
          {generated.map((item) => (
            <div key={item} className="flex gap-2 text-[12px] leading-relaxed text-muted">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
              <span>{item}</span>
            </div>
          ))}
        </div>
        <p className="mt-3 border-t border-border/60 pt-2 text-[11px] leading-relaxed text-muted">
          {lang === "bn"
            ? "সব স্ক্যান descriptive. খবর, দাম, লিকুইডিটি, settlement risk এবং নিজের position size যাচাই না করে trade করবেন না।"
            : "All scans are descriptive. Check news, price action, liquidity, settlement risk and your own position size before trading."}
        </p>
      </details>
    </section>
  );
}

function Boards({
  tab,
  watched,
  onPick,
}: {
  tab: "today" | "value" | "lens";
  watched: boolean;
  onPick: (picked: Picked) => void;
}) {
  const { t } = useLang();
  const [data, setData] = useState<ScannerResponse | null>(null);
  useEffect(() => {
    setData(null);
    let live = true;
    api
      .scannerRadar(tab, watched, tab === "lens" ? 25 : undefined)
      .then((d) => live && setData(d))
      .catch(() => live && setData(null));
    return () => {
      live = false;
    };
  }, [tab, watched]);

  if (!data) return <Spinner />;
  if (data.boards.length === 0) {
    return <Empty>{watched ? t("scanner.emptyWatched") : t("scanner.empty")}</Empty>;
  }
  return (
    <div className="flex flex-col gap-3">
      {/* Same freshness anchor Markets already shows — these boards are EOD-analytics-anchored
          (rankings frozen since the last close) even while the market is currently open; a bare
          per-row '1D' tag with no date anywhere on the page invited "is this today?" confusion. */}
      <div className="flex items-center justify-end px-1 -mb-1.5">
        <FreshnessTag asOf={data.as_of} quoteAsOf={data.quote_as_of} />
      </div>
      <div className="text-[10px] text-muted px-1 -mb-1">{t("mkt.rankNote")}</div>
      {data.boards.map((board) => (
        <BoardCard key={board.key} board={board} regime={data.market_regime} onPick={onPick} />
      ))}
    </div>
  );
}

export function Scanner() {
  const { t, lang } = useLang();
  const { user } = useAuth();
  const [tab, setTab] = useState<Tab>("today");
  const [watched, setWatched] = useState(false);
  const [picked, setPicked] = useState<Picked | null>(null);

  const seg = (id: Tab, label: string) => (
    <button
      onClick={() => setTab(id)}
      className={`flex-1 rounded-full py-1.5 text-sm font-semibold transition ${
        tab === id ? "bg-accent text-bg" : "text-muted"
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="flex flex-col gap-3">
      <div className="px-1">
        <div className="text-lg font-bold">💡 {lang === "bn" ? "আইডিয়া" : "Ideas"}</div>
        <p className="mt-0.5 text-xs leading-snug text-muted">
          {lang === "bn"
            ? "আজকের ডেটা থেকে shortlist — পরামর্শ নয়।"
            : "Shortlists from today's data — not advice."}
        </p>
      </div>

      {/* Pinned below the app header while boards scroll — switching tabs never needs a
          scroll back to the top. -mx-3/px-3 stretches the backdrop across the page gutter. */}
      <div
        className="sticky z-10 -mx-3 px-3 py-1.5 bg-bg/95 backdrop-blur"
        style={{ top: "var(--app-header-h, 96px)" }}
      >
        <div className="flex gap-1 rounded-full border border-border bg-surface p-1">
          {seg("today", t("scanner.today"))}
          {seg("value", t("scanner.value"))}
          {seg("lens", t("scanner.lens"))}
          {seg("watchlist", t("scanner.watchlist"))}
        </div>
      </div>

      {tab === "watchlist" ? (
        <div className="flex flex-col gap-3">
          {user ? (
            <>
              <Boards tab="today" watched onPick={setPicked} />
              <details className="rounded-2xl border border-border bg-surface p-3">
                <summary className="cursor-pointer text-sm font-semibold text-accent">
                  {lang === "bn" ? "ওয়াচলিস্ট দেখুন" : "View watchlist"}
                </summary>
                <div className="mt-3">
                  <Watchlist />
                </div>
              </details>
            </>
          ) : (
            <Watchlist />
          )}
        </div>
      ) : (
        <>
          {user && (
            <div className="flex items-center gap-2 text-xs">
              <span className="text-muted">{t("scanner.scope")}:</span>
              <button
                onClick={() => setWatched(false)}
                className={`rounded-full border px-3 py-1 ${!watched ? "border-accent text-accent" : "border-border text-muted"}`}
              >
                {t("scanner.market")}
              </button>
              <button
                onClick={() => setWatched(true)}
                className={`rounded-full border px-3 py-1 ${watched ? "border-accent text-accent" : "border-border text-muted"}`}
              >
                ⭐ {t("scanner.watched")}
              </button>
            </div>
          )}
          <Boards tab={tab} watched={watched && !!user} onPick={setPicked} />
        </>
      )}

      {/* Pedagogy collapsed — one tap away instead of permanent scroll weight. */}
      <details className="rounded-2xl border border-border bg-surface/60 px-4 py-3">
        <summary className="cursor-pointer text-xs font-semibold text-muted">
          ⓘ {lang === "bn" ? "এই তালিকাগুলো কীভাবে কাজ করে" : "How these lists work"}
        </summary>
        <div className="mt-3">
          <ScannerGuide />
        </div>
      </details>

      {picked && <ScannerSheet picked={picked} onClose={() => setPicked(null)} />}
    </div>
  );
}
