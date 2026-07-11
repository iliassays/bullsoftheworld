import { useEffect, useState } from "react";
import { api, type ScorecardResponse } from "../lib/api";
import { useLang } from "../lib/i18n";

// Factor snapshot + observed cautions. Raw readings are more defensible than pseudo-precise scores
// when a dimension may be represented by only one metric (for example, quality from ROE alone).

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
        <div className="flex items-baseline justify-between">
          <div className="font-semibold text-sm">
            🎯 {bn ? "ফ্যাক্টর স্ন্যাপশট" : "Factor snapshot"}
          </div>
          <div className="text-[10px] text-muted">
            {bn ? "তথ্য" : "as of"} {scorecard.as_of_date}
          </div>
        </div>

        <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2">
          {scorecard.dimensions.map((d) => (
            <div key={d.key} className="rounded-lg border border-border bg-card/50 p-2.5">
              <div className="text-[11px] font-semibold text-muted">{d.label}</div>
              <div className="mt-0.5 text-[13px] font-semibold tnum">
                {d.detail}
              </div>
            </div>
          ))}
        </div>

        <p className="mt-3 border-t border-border pt-2 text-[10.5px] leading-snug text-muted">
          {bn
            ? "প্রতিটি ঘর একটি সীমিত ফ্যাক্টর রিডিং; এটি পূর্ণাঙ্গ কোম্পানি মূল্যায়ন বা কেনা-বেচার সংকেত নয়।"
            : "Each tile is a limited factor reading, not a complete company assessment or trading signal."}
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
