import { useState } from "react";
import { api, ApiError, type Digest } from "../lib/api";

const MOOD: Record<Digest["mood"], { label: string; cls: string }> = {
  bullish: { label: "🐂 Bullish crowd", cls: "text-up" },
  bearish: { label: "🐻 Bearish crowd", cls: "text-down" },
  mixed: { label: "↔ Mixed crowd", cls: "text-muted" },
  quiet: { label: "· Quiet", cls: "text-muted" },
};

// "What's happening" — deterministic, templated digest fusing price action + crowd sentiment.
export function DigestPanel({ code }: { code: string }) {
  const [digest, setDigest] = useState<Digest | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  const load = async () => {
    setLoading(true);
    setErr("");
    try {
      setDigest(await api.digest(code));
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail : "Couldn't load the digest");
    } finally {
      setLoading(false);
    }
  };

  const mood = digest ? MOOD[digest.mood] : null;

  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <div className="flex items-center gap-2">
        <span className="text-accent font-semibold text-sm">
          ✨ What's happening
        </span>
        {digest && mood && (
          <span className={`ml-auto text-xs ${mood.cls}`}>
            {mood.label} · {digest.posts} posts
          </span>
        )}
      </div>

      {!digest && !loading && (
        <button
          onClick={load}
          className="mt-3 text-sm text-bg bg-accent font-bold rounded-full px-4 py-1.5"
        >
          Show what's happening
        </button>
      )}
      {loading && (
        <p className="text-muted text-sm mt-2">
          Reading the tape and the crowd…
        </p>
      )}
      {digest && (
        <p className="text-[15px] leading-relaxed mt-2 text-text/90">
          {digest.summary}
        </p>
      )}
      {err && <p className="text-down text-xs mt-2">{err}</p>}

      <p className="text-[10px] text-muted mt-3">
        Built from delayed price + recent posts. Not financial advice.
      </p>
    </div>
  );
}
