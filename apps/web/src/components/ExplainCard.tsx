import { useState } from "react";
import { api } from "../lib/api";
import { Spinner } from "./ui";

// On-demand AI explainer: the user taps Generate → the API serves a cached plain-language read of
// the stock's technical picture, or generates one via Claude on a cache miss (then caches it for
// the day). Descriptive, educational — not advice. Deliberately not auto-loaded.
export function ExplainCard({ code }: { code: string }) {
  const [text, setText] = useState<string | null>(null);
  const [asOf, setAsOf] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  const run = () => {
    setLoading(true);
    setFailed(false);
    api
      .explainer(code)
      .then((r) => {
        setText(r.explanation);
        setAsOf(r.as_of_date);
      })
      .catch(() => setFailed(true))
      .finally(() => setLoading(false));
  };

  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <div className="text-accent font-semibold text-sm">✨ Explain with AI</div>
      {!text && !loading && (
        <>
          <p className="text-[12px] text-muted mt-1">
            A plain-language read of this stock's technical picture, written on demand.
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
      {text && (
        <>
          <p className="text-[13px] leading-snug mt-2 whitespace-pre-wrap">{text}</p>
          <p className="text-[10px] text-muted mt-2">
            AI-generated from the {asOf ?? "latest"} close · educational, not advice.
          </p>
        </>
      )}
    </div>
  );
}
