import { useEffect, useState } from "react";
import { api, type InvestorLensResponse } from "../lib/api";
import { useLang } from "../lib/i18n";

const ICONS: Record<string, string> = {
  graham_value: "🏷️",
  buffett_quality: "⭐",
  dividend_income: "💵",
  technical_trader: "📈",
  smart_money: "🏦",
  taleb_risk: "🛡️",
};

// Short labels for the at-a-glance strip.
const SHORT: Record<string, { en: string; bn: string }> = {
  graham_value: { en: "Value", bn: "ভ্যালু" },
  buffett_quality: { en: "Quality", bn: "কোয়ালিটি" },
  dividend_income: { en: "Dividend", bn: "লভ্যাংশ" },
  technical_trader: { en: "Trend", bn: "ট্রেন্ড" },
  smart_money: { en: "Smart $", bn: "স্মার্ট মানি" },
  taleb_risk: { en: "Risk", bn: "ঝুঁকি" },
};

// One plain-English (and Bangla) takeaway per lens × verdict — the retail-friendly lead line,
// so a beginner gets the point before the raw ratios.
const PLAIN: Record<string, Record<string, { en: string; bn: string }>> = {
  graham_value: {
    supportive: { en: "Looks cheap versus its peers.", bn: "খাতের তুলনায় সস্তা দেখাচ্ছে।" },
    mixed: { en: "Priced around fair value.", bn: "মোটামুটি ন্যায্য দামে আছে।" },
    caution: { en: "Looks expensive or earnings-weak.", bn: "দামি বা আয় দুর্বল দেখাচ্ছে।" },
    thin_data: { en: "Not enough valuation data.", bn: "ভ্যালুয়েশন ডেটা যথেষ্ট নয়।" },
  },
  buffett_quality: {
    supportive: { en: "Strong, profitable business.", bn: "শক্ত, লাভজনক ব্যবসা।" },
    mixed: { en: "Average business quality.", bn: "মাঝারি ব্যবসার মান।" },
    caution: { en: "Weak profitability.", bn: "লাভজনকতা দুর্বল।" },
    thin_data: { en: "Not enough fundamentals.", bn: "ফান্ডামেন্টাল ডেটা কম।" },
  },
  dividend_income: {
    supportive: { en: "Attractive, earnings-covered dividend.", bn: "আকর্ষণীয়, আয়-সমর্থিত লভ্যাংশ।" },
    mixed: { en: "Modest dividend.", bn: "মাঝারি লভ্যাংশ।" },
    caution: { en: "Little or uncovered dividend.", bn: "কম বা অনিশ্চিত লভ্যাংশ।" },
    thin_data: { en: "Dividend data unavailable.", bn: "লভ্যাংশ ডেটা নেই।" },
  },
  technical_trader: {
    supportive: { en: "Chart trend looks healthy.", bn: "চার্ট ট্রেন্ড ভালো দেখাচ্ছে।" },
    mixed: { en: "Mixed chart signals.", bn: "চার্ট সিগন্যাল মিশ্র।" },
    caution: { en: "Weak or overheated chart.", bn: "চার্ট দুর্বল বা অতিরিক্ত গরম।" },
    thin_data: { en: "Not enough price history.", bn: "দামের ইতিহাস যথেষ্ট নয়।" },
  },
  smart_money: {
    supportive: { en: "Big players added (last disclosure).", bn: "বড় বিনিয়োগকারীরা বাড়িয়েছে (সর্বশেষ ডিসক্লোজার)।" },
    mixed: { en: "Ownership roughly flat.", bn: "মালিকানা প্রায় অপরিবর্তিত।" },
    caution: { en: "Big players trimmed.", bn: "বড় বিনিয়োগকারীরা কমিয়েছে।" },
    thin_data: { en: "No ownership data.", bn: "মালিকানার ডেটা নেই।" },
  },
  taleb_risk: {
    supportive: { en: "Liquid — easier to exit.", bn: "লিকুইড — বের হওয়া সহজ।" },
    mixed: { en: "Moderate exit risk.", bn: "মাঝারি এক্সিট ঝুঁকি।" },
    caution: { en: "Illiquid/fragile — hard to exit.", bn: "পাতলা/ভঙ্গুর — বের হওয়া কঠিন।" },
    thin_data: { en: "Not enough liquidity data.", bn: "লিকুইডিটি ডেটা কম।" },
  },
};

function verdictStyle(v: string): string {
  if (v === "supportive") return "text-up bg-up/10 border-up/25";
  if (v === "caution") return "text-down bg-down/10 border-down/25";
  if (v === "thin_data") return "text-muted bg-card border-border";
  return "text-accent bg-accent/10 border-accent/25";
}

function verdictDot(v: string): string {
  if (v === "supportive") return "bg-up";
  if (v === "caution") return "bg-down";
  if (v === "thin_data") return "bg-muted";
  return "bg-accent";
}

function verdictLabel(v: string, bn: boolean): string {
  if (v === "supportive") return bn ? "সহায়ক" : "Supportive";
  if (v === "caution") return bn ? "সতর্ক" : "Caution";
  if (v === "thin_data") return bn ? "ডেটা কম" : "Thin data";
  return bn ? "মিশ্র" : "Mixed";
}

function plainRead(key: string, verdict: string, bn: boolean): string {
  const p = PLAIN[key]?.[verdict];
  return p ? (bn ? p.bn : p.en) : "";
}

function shortName(key: string, fallback: string, bn: boolean): string {
  const s = SHORT[key];
  return s ? (bn ? s.bn : s.en) : fallback;
}

function checkDot(status: string): string {
  if (status === "pass") return "bg-up";
  if (status === "fail") return "bg-down";
  if (status === "na") return "bg-muted";
  return "bg-accent"; // watch
}

export function InvestorLensCard({ code }: { code: string }) {
  const { lang } = useLang();
  const bn = lang === "bn";
  const [data, setData] = useState<InvestorLensResponse | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setData(null);
    setFailed(false);
    let live = true;
    api
      .investorLens(code)
      .then((d) => live && setData(d))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [code, lang]);

  if (failed) return null;
  if (!data)
    return <div className="bg-surface border border-border rounded-2xl p-4 animate-pulse h-64" />;

  return (
    <section className="bg-surface border border-border rounded-2xl p-4">
      <div className="font-semibold text-sm">🧠 Investor Lens</div>
      <p className="text-[12px] text-muted mt-0.5 leading-snug">
        {bn
          ? "একই তথ্য বিভিন্ন বিনিয়োগ-স্টাইল কীভাবে পড়ে। পরামর্শ নয়।"
          : "How different investing styles read the same facts. Not advice."}
      </p>

      {/* at-a-glance: every lens as a colored chip, readable in one glance */}
      <div className="mt-3 flex flex-wrap gap-1.5">
        {data.lenses.map((l) => (
          <span
            key={l.key}
            className={`flex items-center gap-1.5 text-[11px] font-semibold rounded-full border px-2 py-1 ${verdictStyle(
              l.verdict,
            )}`}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${verdictDot(l.verdict)}`} />
            {shortName(l.key, l.name, bn)}
            {l.score != null ? ` ${l.score}` : ""}
          </span>
        ))}
      </div>

      <div className="mt-4 grid gap-3">
        {data.lenses.map((l) => (
          <article key={l.key} className="rounded-xl border border-border bg-card/50 p-3">
            <div className="flex items-start gap-2">
              <span className="text-lg leading-none">{ICONS[l.key] ?? "•"}</span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <h3 className="text-sm font-bold">{l.name}</h3>
                  <span
                    className={`text-[10px] font-bold rounded-full border px-2 py-0.5 ${verdictStyle(
                      l.verdict,
                    )}`}
                  >
                    {verdictLabel(l.verdict, bn)}
                    {l.score != null ? ` · ${l.score}/10` : ""}
                  </span>
                </div>
                {/* plain-English takeaway leads; the persona/ratios are secondary detail */}
                <p className="text-[13px] font-semibold mt-1 leading-snug">
                  {plainRead(l.key, l.verdict, bn) || l.summary}
                </p>
              </div>
            </div>

            <p className="mt-2 text-[11px] text-muted leading-snug">{l.summary}</p>

            {/* have-vs-want: your value against the style's benchmark, so the gap is visible */}
            {l.checks && l.checks.length > 0 ? (
              <div className="mt-2 flex flex-col gap-1">
                {l.checks.map((c, i) => (
                  <div key={i} className="flex items-center gap-2 text-[12px]">
                    <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${checkDot(c.status)}`} />
                    <span className="text-muted flex-1 min-w-0 truncate">{c.label}</span>
                    <span className="text-text font-semibold tnum">{c.actual}</span>
                    {c.expected && c.expected !== "—" && (
                      <span className="text-muted tnum">
                        {bn ? "চাই" : "want"} {c.expected}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <ul className="mt-2 flex flex-col gap-1">
                {l.points.map((p, i) => (
                  <li key={i} className="text-[12px] text-muted leading-snug tnum">
                    <span className="text-text">•</span> {p}
                  </li>
                ))}
              </ul>
            )}

            {/* what to verify next (the lens can't see these) — only when there's anything left */}
            {l.watch_next.length > 0 && (
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                <span className="text-[10.5px] text-muted font-semibold">
                  {bn ? "এরপর যাচাই করুন:" : "Check next:"}
                </span>
                {l.watch_next.map((w) => (
                  <span
                    key={w}
                    className="text-[10.5px] text-muted border border-border rounded-full px-2 py-0.5"
                  >
                    {w}
                  </span>
                ))}
              </div>
            )}

          </article>
        ))}
      </div>

      <p className="mt-3 border-t border-border pt-2 text-[11px] leading-snug text-muted">
        {bn
          ? `${data.as_of_date} ক্লোজের ভিত্তিতে · প্রতি ট্রেডিং দিনের ক্লোজের পর আপডেট হয়; ফান্ডামেন্টাল কোম্পানির রিপোর্টে বদলায়।`
          : `Based on the ${data.as_of_date} close · updates after each trading day's close; fundamentals change when companies report.`}
      </p>
      <p className="mt-1 text-[10.5px] leading-snug text-muted">{data.disclaimer}</p>
    </section>
  );
}
