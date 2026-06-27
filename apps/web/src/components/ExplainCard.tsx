import { useState } from "react";
import { api } from "../lib/api";
import { Spinner } from "./ui";

// On-demand AI explainer: the user taps Generate → the API serves a cached plain-language read of
// the stock's technical picture, or generates one via Claude on a cache miss (then caches it for
// the day). Descriptive, educational — not advice. Deliberately not auto-loaded.
// Small icon per point category.
const TAG_ICON: Record<string, string> = {
  chart: "📉",
  fundamentals: "💪",
  trend: "⏱️",
  crowd: "🗣️",
};

interface Read {
  headline: string;
  asOf: string;
  points: { tag: string; text: string }[];
}

export function ExplainCard({ code }: { code: string }) {
  const [read, setRead] = useState<Read | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  const run = () => {
    setLoading(true);
    setFailed(false);
    api
      .explainer(code)
      .then((r) => setRead({ headline: r.headline, asOf: r.as_of_date, points: r.points }))
      .catch(() => setFailed(true))
      .finally(() => setLoading(false));
  };

  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <div className="text-accent font-semibold text-sm">✨ Deeper analysis</div>
      {!read && !loading && (
        <>
          <p className="text-[12px] text-muted mt-1">
            A fuller written read — the chart, fundamentals, who's buying, and the trend woven into
            one plain-language picture. Written on demand.
          </p>
          <button
            onClick={run}
            className="mt-2 text-xs font-semibold px-3 py-1.5 rounded-full border text-accent border-accent bg-accent/10"
          >
            Generate
          </button>
        </>
      )}
      {loading && (
        <div className="mt-3">
          <Spinner />
        </div>
      )}
      {failed && !loading && (
        <p className="text-[12px] text-down mt-2">
          Couldn't generate right now.{" "}
          <button onClick={run} className="text-accent font-semibold">
            Try again
          </button>
        </p>
      )}
      {read && (
        <>
          <p className="text-[15px] font-semibold mt-1 leading-snug">{read.headline}</p>
          <ul className="mt-3 flex flex-col gap-1.5">
            {read.points.map((p, i) => (
              <li key={i} className="flex gap-2 text-[13px] leading-snug">
                <span className="shrink-0">{TAG_ICON[p.tag] ?? "•"}</span>
                <span>{p.text}</span>
              </li>
            ))}
          </ul>
          <p className="text-[10px] text-muted mt-2">
            AI-generated from the {read.asOf} close · educational, not advice.
          </p>
        </>
      )}
    </div>
  );
}
