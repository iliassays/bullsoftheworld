import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Spinner } from "./ui";

// AI explainer: auto-loads on view. The API serves a cached plain-language read (headline + labelled
// points) of the stock's whole picture, or generates one via Claude on a cache miss — the cache key
// includes the data's as_of_date, so it regenerates automatically when new EOD data lands.
// Descriptive, educational — not advice.
const TAG_ICON: Record<string, string> = {
  chart: "📊",
  value: "🏷️",
  quality: "⭐",
  income: "💵",
  trend: "📈",
  crowd: "🗣️",
};

interface Read {
  headline: string;
  asOf: string;
  points: { tag: string; text: string }[];
}

export function ExplainCard({ code }: { code: string }) {
  const [read, setRead] = useState<Read | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    setRead(null);
    setFailed(false);
    setLoading(true);
    api
      .explainer(code)
      .then((r) => {
        if (live) setRead({ headline: r.headline, asOf: r.as_of_date, points: r.points });
      })
      .catch(() => live && setFailed(true))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [code]);

  if (failed) return null; // degrade silently — the free Plain read above already covers the basics

  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <div className="text-accent font-semibold text-sm">✨ Deeper analysis</div>
      {loading || !read ? (
        <div className="mt-3">
          <Spinner />
        </div>
      ) : (
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
