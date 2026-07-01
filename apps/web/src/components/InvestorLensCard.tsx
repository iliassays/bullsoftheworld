import { useEffect, useState } from "react";
import { api, type InvestorLensResponse } from "../lib/api";
import { useLang } from "../lib/i18n";

const ICONS: Record<string, string> = {
  graham_value: "🏷️",
  buffett_quality: "⭐",
  technical_trader: "📈",
  smart_money: "🏦",
  taleb_risk: "🛡️",
};

function verdictStyle(v: string): string {
  if (v === "supportive") return "text-up bg-up/10 border-up/25";
  if (v === "caution") return "text-down bg-down/10 border-down/25";
  if (v === "thin_data") return "text-muted bg-card border-border";
  return "text-accent bg-accent/10 border-accent/25";
}

function verdictLabel(v: string, bn: boolean): string {
  if (v === "supportive") return bn ? "সহায়ক" : "Supportive";
  if (v === "caution") return bn ? "সতর্ক" : "Caution";
  if (v === "thin_data") return bn ? "ডেটা কম" : "Thin data";
  return bn ? "মিশ্র" : "Mixed";
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
    return (
      <div className="bg-surface border border-border rounded-2xl p-4 animate-pulse h-64" />
    );

  return (
    <section className="bg-surface border border-border rounded-2xl p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-semibold text-sm">
            🧠 {bn ? "Investor Lens" : "Investor Lens"}
          </div>
          <p className="text-[15px] font-semibold mt-1 leading-snug">
            {data.headline}
          </p>
        </div>
        <span className="text-[10px] text-muted shrink-0 tnum">
          {bn ? "তথ্য" : "as of"} {data.as_of_date}
        </span>
      </div>

      <div className="mt-4 grid gap-3">
        {data.lenses.map((l) => (
          <article
            key={l.key}
            className="rounded-xl border border-border bg-card/50 p-3"
          >
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
                <div className="text-[11px] text-muted mt-0.5">{l.persona}</div>
              </div>
            </div>

            <p className="mt-2 text-[13px] leading-snug">{l.summary}</p>

            <ul className="mt-2 flex flex-col gap-1">
              {l.points.map((p, i) => (
                <li key={i} className="text-[12px] text-muted leading-snug">
                  <span className="text-text">•</span> {p}
                </li>
              ))}
            </ul>

            <div className="mt-2 flex flex-wrap gap-1.5">
              {l.watch_next.map((w) => (
                <span
                  key={w}
                  className="text-[10.5px] text-muted border border-border rounded-full px-2 py-0.5"
                >
                  {w}
                </span>
              ))}
            </div>
          </article>
        ))}
      </div>

      <p className="mt-3 border-t border-border pt-2 text-[10.5px] leading-snug text-muted">
        {data.disclaimer}
      </p>
    </section>
  );
}
