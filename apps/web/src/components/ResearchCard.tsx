import { useEffect, useState } from "react";
import { api, type ResearchBrief } from "../lib/api";
import { useLang } from "../lib/i18n";
import { Spinner } from "./ui";

const QUESTIONS = [
  { en: "Why is this moving?", bn: "এটি কেন নড়ছে?" },
  { en: "Is there official news?", bn: "অফিশিয়াল খবর আছে?" },
  { en: "Explain latest news", bn: "সর্বশেষ খবর বুঝিয়ে বলুন" },
  { en: "Any red flags?", bn: "কোনো ঝুঁকির সংকেত আছে?" },
  { en: "What are people saying?", bn: "মানুষ কী বলছে?" },
];

const QUALITY: Record<ResearchBrief["evidence_quality"], string> = {
  strong: "Strong evidence",
  mixed: "Mixed evidence",
  weak: "Weak evidence",
};

const QUALITY_BN: Record<ResearchBrief["evidence_quality"], string> = {
  strong: "শক্ত প্রমাণ",
  mixed: "মিশ্র প্রমাণ",
  weak: "দুর্বল প্রমাণ",
};

const REL: Record<string, string> = {
  official: "DSE",
  market: "Market",
  system: "Signal",
  crowd: "Crowd",
};

const LENS: Record<string, string> = {
  valuation: "Valuation",
  technical: "Technical",
  liquidity: "Flow",
  ownership: "Ownership",
  disclosure: "Disclosure",
  crowd: "Crowd",
};

const LENS_BN: Record<string, string> = {
  valuation: "ভ্যালুয়েশন",
  technical: "টেকনিক্যাল",
  liquidity: "ফ্লো",
  ownership: "মালিকানা",
  disclosure: "ডিসক্লোজার",
  crowd: "ক্রাউড",
};

const STANCE: Record<string, string> = {
  constructive: "bg-up/10 text-up border-up/20",
  watch: "bg-accent/10 text-accent border-accent/20",
  risk: "bg-down/10 text-down border-down/20",
  unknown: "bg-muted/10 text-muted border-border",
};

function dateShort(date: string | null): string {
  if (!date) return "";
  return date.slice(0, 10);
}

export function ResearchCard({ code }: { code: string }) {
  const { t, lang } = useLang();
  const bn = lang === "bn";
  const [question, setQuestion] = useState(QUESTIONS[0].en);
  const [brief, setBrief] = useState<ResearchBrief | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setQuestion(QUESTIONS[0].en);
    setBrief(null);
    setFailed(false);
    setLoading(false);
  }, [code]);

  const load = (q = question) => {
    setQuestion(q);
    setLoading(true);
    setFailed(false);
    api
      .research(code, q)
      .then(setBrief)
      .catch(() => setFailed(true))
      .finally(() => setLoading(false));
  };

  return (
    <section className="bg-surface border border-border rounded-2xl p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-semibold text-sm">🔎 {t("research.title")}</div>
          <p className="text-[13px] text-muted mt-1 leading-snug">{t("research.hint")}</p>
        </div>
        {brief && (
          <div
            className={`shrink-0 rounded-full px-2 py-1 text-[10px] font-semibold ${
              brief.evidence_quality === "strong"
                ? "bg-up/10 text-up"
                : brief.evidence_quality === "mixed"
                  ? "bg-accent/10 text-accent"
                  : "bg-down/10 text-down"
            }`}
          >
            {bn ? QUALITY_BN[brief.evidence_quality] : QUALITY[brief.evidence_quality]}
          </div>
        )}
      </div>

      <div className="mt-3 flex gap-2 overflow-x-auto pb-1">
        {QUESTIONS.map((q) => {
          const label = bn ? q.bn : q.en;
          const active = brief?.question === q.en || (!brief && question === q.en);
          return (
            <button
              key={q.en}
              onClick={() => load(q.en)}
              className={`shrink-0 rounded-full border px-3 py-1.5 text-xs font-semibold ${
                active
                  ? "border-accent bg-accent/10 text-accent"
                  : "border-border text-muted hover:border-accent hover:text-accent"
              }`}
            >
              {label}
            </button>
          );
        })}
      </div>

      {!brief && !loading && !failed && (
        <button
          onClick={() => load()}
          className="mt-3 bg-accent text-bg font-bold rounded-xl px-4 py-2 text-sm"
        >
          {t("research.cta")}
        </button>
      )}

      {loading && (
        <div className="mt-3">
          <Spinner />
        </div>
      )}

      {failed && !loading && (
        <button onClick={() => load()} className="mt-3 text-down text-[13px] font-semibold">
          {t("research.retry")}
        </button>
      )}

      {brief && !loading && (
        <div className="mt-3">
          <p className="text-[14px] leading-relaxed">{brief.answer}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <span
              className={`rounded-full px-2 py-1 text-[10px] font-semibold ${
                brief.official_catalyst ? "bg-up/10 text-up" : "bg-muted/10 text-muted"
              }`}
            >
              {brief.official_catalyst ? t("research.officialYes") : t("research.officialNo")}
            </span>
            {brief.blocked_advice && (
              <span className="rounded-full px-2 py-1 text-[10px] font-semibold bg-down/10 text-down">
                {t("research.adviceBlocked")}
              </span>
            )}
          </div>

          {(brief.insights ?? []).length > 0 && (
            <div className="mt-4">
              <div className="text-[11px] font-semibold text-muted mb-2">
                {t("research.insights")}
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                {(brief.insights ?? []).slice(0, 6).map((insight) => (
                  <div
                    key={`${insight.lens}:${insight.title}`}
                    className={`rounded-xl border p-3 ${STANCE[insight.stance] ?? STANCE.unknown}`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[10px] font-bold uppercase tracking-wide">
                        {(bn ? LENS_BN : LENS)[insight.lens] ?? insight.lens}
                      </span>
                      <span className="text-[10px] font-semibold capitalize">{insight.stance}</span>
                    </div>
                    <div className="mt-1 text-[13px] font-semibold leading-snug">
                      {insight.title}
                    </div>
                    <p className="mt-1 text-[12px] leading-snug opacity-90">{insight.detail}</p>
                    <div className="mt-2 text-[11px] font-semibold opacity-80">
                      {insight.evidence}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {brief.sources.length > 0 && (
            <div className="mt-4">
              <div className="text-[11px] font-semibold text-muted mb-2">
                {t("research.sources")}
              </div>
              <div className="flex flex-col gap-2">
                {brief.sources.slice(0, 4).map((s) => (
                  <div key={`${s.type}:${s.id}`} className="rounded-xl border border-border p-3">
                    <div className="flex items-center gap-2 text-[11px] text-muted">
                      <span className="font-bold text-accent">{REL[s.reliability] ?? s.type}</span>
                      {dateShort(s.date) && <span className="tnum">{dateShort(s.date)}</span>}
                    </div>
                    <div className="mt-1 text-[13px] font-semibold leading-snug">{s.title}</div>
                    <p className="mt-1 text-[12px] text-muted leading-snug">{s.snippet}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          <p className="text-[10px] text-muted mt-3">{t("research.footer")}</p>
        </div>
      )}
    </section>
  );
}
