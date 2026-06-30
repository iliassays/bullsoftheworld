import { useState } from "react";
import { api, ApiError, type Digest } from "../lib/api";
import { useLang } from "../lib/i18n";

const MOOD: Record<Digest["mood"], { key: string; cls: string }> = {
  bullish: { key: "mood.bullish", cls: "text-up" },
  bearish: { key: "mood.bearish", cls: "text-down" },
  mixed: { key: "mood.mixed", cls: "text-muted" },
  quiet: { key: "mood.quiet", cls: "text-muted" },
};

// "What's happening" — deterministic, templated digest fusing price action + crowd sentiment.
export function DigestPanel({ code }: { code: string }) {
  const { t } = useLang();
  const [digest, setDigest] = useState<Digest | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  const load = async () => {
    setLoading(true);
    setErr("");
    try {
      setDigest(await api.digest(code));
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail : t("digest.error"));
    } finally {
      setLoading(false);
    }
  };

  const mood = digest ? MOOD[digest.mood] : null;

  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <div className="flex items-center gap-2">
        <span className="font-semibold text-sm">
          🗣️ {t("digest.title")}
        </span>
        {digest && mood && (
          <span className={`ml-auto text-xs ${mood.cls}`}>
            {t(mood.key)} · {digest.posts} {t("posts")}
          </span>
        )}
      </div>

      {!digest && !loading && (
        <button
          onClick={load}
          className="mt-3 text-sm text-bg bg-accent font-bold rounded-full px-4 py-1.5"
        >
          {t("digest.show")}
        </button>
      )}
      {loading && (
        <p className="text-muted text-sm mt-2">{t("digest.loading")}</p>
      )}
      {digest && (
        <p className="text-[15px] leading-relaxed mt-2 text-text/90">
          {digest.summary}
        </p>
      )}
      {err && <p className="text-down text-xs mt-2">{err}</p>}

      <p className="text-[10px] text-muted mt-3">{t("digest.footer")}</p>
    </div>
  );
}
