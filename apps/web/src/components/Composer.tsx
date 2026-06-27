import { useState } from "react";
import { api, ApiError, type Post } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useLang } from "../lib/i18n";

export function Composer({
  onPosted,
  initial = "",
  parentId,
  compact = false,
  placeholder,
}: {
  onPosted: (p: Post) => void;
  initial?: string;
  parentId?: number;
  compact?: boolean; // replies hide the bull/bear selector
  placeholder?: string;
}) {
  const { user } = useAuth();
  const { t } = useLang();
  const ph = placeholder ?? t("composer.placeholder");
  const [body, setBody] = useState(initial);
  const [sentiment, setSentiment] = useState<"bull" | "bear" | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  if (!user) return null;

  const submit = async () => {
    if (!body.trim()) return;
    setBusy(true);
    setErr("");
    try {
      const post = await api.createPost({
        body: body.trim(),
        sentiment,
        parent_id: parentId,
      });
      onPosted(post);
      setBody("");
      setSentiment(null);
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail : t("composer.failed"));
    } finally {
      setBusy(false);
    }
  };

  const tone = (s: "bull" | "bear") =>
    `text-xs font-bold px-3 py-1.5 rounded-full border transition ${
      sentiment === s
        ? s === "bull"
          ? "text-up border-up bg-up/10"
          : "text-down border-down bg-down/10"
        : "text-muted border-border"
    }`;

  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder={ph}
        rows={compact ? 2 : 3}
        className="w-full bg-transparent resize-none outline-none text-[15px] placeholder:text-muted"
      />
      <div className="flex items-center gap-2 mt-2">
        {!compact && (
          <>
            <button
              type="button"
              className={tone("bull")}
              onClick={() => setSentiment(sentiment === "bull" ? null : "bull")}
            >
              {t("composer.bull")}
            </button>
            <button
              type="button"
              className={tone("bear")}
              onClick={() => setSentiment(sentiment === "bear" ? null : "bear")}
            >
              {t("composer.bear")}
            </button>
          </>
        )}
        <button
          type="button"
          disabled={busy || !body.trim()}
          onClick={submit}
          className="ml-auto bg-accent text-bg font-bold text-sm px-4 py-1.5 rounded-full disabled:opacity-40"
        >
          {busy ? "…" : compact ? t("common.reply") : t("common.post")}
        </button>
      </div>
      {err && <p className="text-down text-xs mt-2">{err}</p>}
    </div>
  );
}
