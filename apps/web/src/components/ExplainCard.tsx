import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useLang } from "../lib/i18n";
import { Spinner } from "./ui";

// AI explainer: loads on demand (button click), not on view — generating via Claude for every page
// view was a wasted API call when most visitors never read it. The API serves a cached plain-language
// read (headline + labelled points) of the stock's whole picture, or generates one via Claude on a
// cache miss (keyed by the data's as_of_date, so it refreshes when new EOD data lands). Descriptive,
// educational — not advice.
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
  const { t } = useLang();
  const [read, setRead] = useState<Read | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [started, setStarted] = useState(false);

  // Reset to the un-started (button) state whenever the stock changes — don't show one stock's
  // analysis under another, and don't auto-fetch.
  useEffect(() => {
    setRead(null);
    setFailed(false);
    setLoading(false);
    setStarted(false);
  }, [code]);

  const load = () => {
    setStarted(true);
    setFailed(false);
    setLoading(true);
    api
      .explainer(code)
      .then((r) => setRead({ headline: r.headline, asOf: r.as_of_date, points: r.points }))
      .catch(() => setFailed(true))
      .finally(() => setLoading(false));
  };

  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <div className="font-semibold text-sm">✨ {t("explain.title")}</div>

      {!started && (
        <>
          <p className="text-[13px] text-muted mt-1 leading-snug">{t("explain.hint")}</p>
          <button
            onClick={load}
            className="mt-3 bg-accent text-bg font-bold rounded-xl px-4 py-2 text-sm"
          >
            {t("explain.cta")}
          </button>
        </>
      )}

      {started && loading && (
        <div className="mt-3">
          <Spinner />
        </div>
      )}

      {started && failed && (
        <button onClick={load} className="mt-3 text-down text-[13px] font-semibold">
          {t("explain.retry")}
        </button>
      )}

      {started && !loading && read && (
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
            {t("explain.aiPrefix")} {read.asOf} {t("explain.aiSuffix")}
          </p>
        </>
      )}
    </div>
  );
}
