import { useEffect, useState } from "react";
import { api, type InvestorLensItem, type InvestorLensResponse } from "../lib/api";
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
  if (v === "supportive") return bn ? "মূল ফ্যাক্টর সহায়ক" : "Core supportive";
  if (v === "caution") return bn ? "মূল ফ্যাক্টরে সতর্কতা" : "Core caution";
  if (v === "thin_data") return bn ? "ডেটা কম" : "Thin data";
  return bn ? "মূল ফ্যাক্টর মিশ্র" : "Core mixed";
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

function checkSummary(lens: InvestorLensItem, bn: boolean) {
  const checks = lens.checks ?? [];
  const pass = checks.filter((check) => check.status === "pass").length;
  const missing = checks.filter((check) => check.status === "na").length;
  const assessed = checks.length - missing;
  const label =
    assessed === 0
      ? bn
        ? "পরীক্ষার তথ্য নেই"
        : "No assessed checks"
      : bn
        ? `বাড়তি পরীক্ষায় ${assessed}টির মধ্যে ${pass}টি উত্তীর্ণ${missing ? ` · ${missing}টি তথ্য নেই` : ""}`
        : `${pass}/${assessed} extended checks pass${missing ? ` · ${missing} unavailable` : ""}`;
  return label;
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
      <div className="font-semibold text-sm">🧠 {bn ? "বিনিয়োগ বিশ্লেষণ" : "Investor Lens"}</div>
      <p className="text-[12px] text-muted mt-0.5 leading-snug">
        {bn
          ? "একই তথ্য বিভিন্ন বিনিয়োগ-স্টাইল কীভাবে পড়ে। পরামর্শ নয়।"
          : "How different investing styles read the same facts. Not advice."}
      </p>
      <p className="mt-1 text-[10.5px] leading-snug text-muted">
        {bn
          ? "মূল স্কোর পুরো বাজারে তুলনাযোগ্য ফ্যাক্টর ব্যবহার করে; নিচের বাড়তি পরীক্ষাগুলো ঋণ, ইতিহাস ও অনুপস্থিত তথ্যের প্রেক্ষাপট যোগ করে।"
          : "The core score uses market-wide comparable factors; extended checks add debt, history, and missing-data context."}
      </p>

      {/* at-a-glance: every lens as a colored chip, readable in one glance */}
      <div className="mt-3 flex flex-wrap gap-1.5">
        {data.lenses.map((l) => {
          return (
            <span
              key={l.key}
              className={`flex items-center gap-1.5 text-[11px] font-semibold rounded-full border px-2 py-1 ${verdictStyle(
                l.verdict,
              )}`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${verdictDot(l.verdict)}`} />
              {shortName(l.key, l.name, bn)}
            </span>
          );
        })}
      </div>

      <div className="mt-4 grid gap-3">
        {data.lenses.map((l) => {
          const checks = checkSummary(l, bn);
          return (
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
                  </span>
                </div>
                {/* Backend score/verdict is authoritative. Check rows add context but do not
                    silently create a competing frontend rating. */}
                <p className="text-[13px] font-semibold mt-1 leading-snug">
                  {l.score == null
                    ? checks
                    : `${bn ? "মূল স্কোর" : "Core score"} ${l.score}/10 · ${checks}`}
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
          );
        })}
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
