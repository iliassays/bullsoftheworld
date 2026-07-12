import { useEffect, useState } from "react";
import { api, type ScorecardResponse } from "../lib/api";
import { useLang } from "../lib/i18n";
import { FreshnessTag } from "./FreshnessTag";

// Independent factor readings. Each score stays beside its raw input and benchmark so it cannot
// masquerade as a black-box overall rating.

export function ScorecardCard({ code }: { code: string }) {
  const { lang } = useLang();
  const [data, setData] = useState<ScorecardResponse | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setData(null);
    setFailed(false);
    let live = true;
    api
      .scorecard(code)
      .then((d) => live && setData(d))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [code, lang]);

  if (failed) return null;
  if (!data)
    return (
      <div className="bg-surface border border-border rounded-2xl p-4 animate-pulse h-40" />
    );

  const bn = lang === "bn";
  const { scorecard, red_flags } = data;

  return (
    <>
      <div className="bg-surface border border-border rounded-2xl p-4">
        <div>
          <div className="font-semibold text-sm">
            🎯 {bn ? "ফ্যাক্টর স্ন্যাপশট" : "Factor snapshot"}
          </div>
          <FreshnessTag asOf={scorecard.as_of_date} className="mt-1" />
        </div>

        <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-3">
          {scorecard.dimensions.map((d) => (
            <div key={d.key} className="border-t border-border pt-2.5">
              <div className="flex items-center justify-between gap-2">
                <div className="text-[11px] font-semibold text-muted">{d.label}</div>
                <span
                  className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold tnum ${
                    d.score >= 8
                      ? "bg-up/10 text-up"
                      : d.score >= 6
                        ? "bg-accent/10 text-accent"
                        : d.score >= 4
                          ? "bg-border/60 text-text"
                          : "bg-down/10 text-down"
                  }`}
                >
                  {d.score}/10 · {d.assessment}
                </span>
              </div>
              <div className="mt-0.5 text-[13px] font-semibold tnum">
                {d.detail}
              </div>
              <div className="mt-1.5 text-[10px] leading-snug text-muted">{d.benchmark}</div>
            </div>
          ))}
        </div>

        <p className="mt-3 border-t border-border pt-2 text-[10.5px] leading-snug text-muted">
          {bn
            ? "৮–১০ শক্তিশালী, ৬–৭ সহায়ক, ৪–৫ মিশ্র, ০–৩ দুর্বল। প্রতিটি ফ্যাক্টর আলাদা; এগুলো যোগ করে কেনা-বেচার সিদ্ধান্ত নেওয়া যাবে না।"
            : "8–10 is strong, 6–7 supportive, 4–5 mixed, and 0–3 weak for that factor. Factors are independent and must not be added into a buy/sell verdict."}
        </p>
      </div>

      <div className="bg-surface border border-border rounded-2xl p-4">
        <div className="flex items-center justify-between">
          <div className="font-semibold text-sm">
            🚩 {bn ? "পর্যবেক্ষিত সতর্কতা" : "Observed cautions"}
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          {red_flags.clean ? (
            <p className="text-[12px] text-muted">
              {bn
                ? "এই সীমিত স্বয়ংক্রিয় পরীক্ষায় কোনো সতর্কতা ধরা পড়েনি। এটি সম্পূর্ণ ঝুঁকি পর্যালোচনা নয়।"
                : "No cautions were detected by these limited automated checks. This is not a complete risk review."}
            </p>
          ) : (
            red_flags.flags.map((f) => (
              <span
                key={f.key}
                className="text-[11.5px] text-down bg-down/10 border border-down/25 rounded-lg px-2.5 py-1"
              >
                🚩 {f.label}
              </span>
            ))
          )}
        </div>

        <p className="mt-3 text-[11px] text-center text-muted">{red_flags.note}</p>
      </div>
    </>
  );
}
