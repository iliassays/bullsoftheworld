import { useEffect, useState } from "react";
import { api, type ScorecardResponse } from "../lib/api";
import { useLang } from "../lib/i18n";

// Stock Scorecard + Red Flags. One endpoint, two cards. Dimensions-only (no composite verdict);
// each score shows the metric behind it. Red flags are descriptive cautions, never "don't buy".

function barColor(score: number): string {
  return score >= 7 ? "bg-up" : score >= 4 ? "bg-accent" : "bg-down";
}
function scoreColor(score: number): string {
  return score >= 7 ? "text-up" : score >= 4 ? "text-accent" : "text-down";
}

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
          <div className="text-accent font-semibold text-sm">
            🎯 {bn ? "স্কোরকার্ড" : "Scorecard"}
          </div>
          <div className="text-[10px] text-muted">
            {bn ? "তথ্য" : "as of"} {scorecard.as_of_date}
          </div>
        </div>

        <div className="mt-3 flex flex-col gap-2.5">
          {scorecard.dimensions.map((d) => (
            <div key={d.key} className="flex items-center gap-3">
              <div className="w-24 shrink-0 text-[13px] font-semibold">{d.label}</div>
              <div className="flex-1 h-2 rounded-full bg-card overflow-hidden">
                <div
                  className={`h-full rounded-full ${barColor(d.score)}`}
                  style={{ width: `${d.score * 10}%` }}
                />
              </div>
              <div className={`w-9 shrink-0 text-right font-bold text-[13px] ${scoreColor(d.score)}`}>
                {d.score}
                <span className="text-muted text-[10px] font-semibold">/10</span>
              </div>
            </div>
          ))}
        </div>

        {/* The metric behind each score, inline — transparency, not a black box. */}
        <div className="mt-2.5 flex flex-col gap-1">
          {scorecard.dimensions.map((d) => (
            <div key={d.key} className="text-[11px] text-muted">
              <span className="text-text">{d.label}:</span> {d.detail}
            </div>
          ))}
        </div>

        <p className="mt-3 border-t border-border pt-2 text-[10.5px] leading-snug text-muted">
          {scorecard.disclaimer}
        </p>
      </div>

      <div className="bg-surface border border-border rounded-2xl p-4">
        <div className="flex items-center justify-between">
          <div className="text-accent font-semibold text-sm">
            🚩 {bn ? "রেড ফ্ল্যাগ" : "Red Flags"}
          </div>
          {red_flags.clean && (
            <span className="text-[11px] font-bold text-up bg-up/10 border border-up/30 rounded-full px-2.5 py-1">
              ✓ {bn ? "পরিষ্কার" : "Clean"}
            </span>
          )}
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          {red_flags.clean ? (
            <p className="text-[12px] text-muted">
              {bn
                ? "এই শেয়ারে কোনো রেড ফ্ল্যাগ নেই।"
                : "No red flags on this stock."}
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
