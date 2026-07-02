import { useEffect, useRef, useState } from "react";
import { CompanyLogo } from "./CompanyLogo";
import { api, ApiError, type Post, type SymbolOut } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useLang } from "../lib/i18n";
import { loadSymbols } from "../lib/symbols";

// Find the ticker token the caret is currently inside, if any: a `$` or `@` trigger at the
// start of a word followed only by ticker chars up to the caret. We always insert `$CODE`
// (the canonical cashtag the app links), whichever trigger the user typed.
function tokenAt(
  text: string,
  caret: number,
): { start: number; query: string } | null {
  let i = caret - 1;
  while (i >= 0 && /[A-Za-z0-9]/.test(text[i])) i--;
  if (
    i >= 0 &&
    (text[i] === "$" || text[i] === "@") &&
    (i === 0 || /\s/.test(text[i - 1]))
  ) {
    return { start: i, query: text.slice(i + 1, caret) };
  }
  return null;
}

export function Composer({
  onPosted,
  initial = "",
  parentId,
  routeCode,
  compact = false,
  placeholder,
}: {
  onPosted: (p: Post) => void;
  initial?: string;
  parentId?: number;
  routeCode?: string;
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
  const [notice, setNotice] = useState("");

  // Ticker autocomplete
  const taRef = useRef<HTMLTextAreaElement>(null);
  const [symbols, setSymbols] = useState<SymbolOut[]>([]);
  const [suggest, setSuggest] = useState<{
    start: number;
    query: string;
  } | null>(null);
  const [sel, setSel] = useState(0);

  useEffect(() => {
    loadSymbols().then(setSymbols);
  }, []);

  if (!user) return null;

  const q = (suggest?.query ?? "").toUpperCase();
  const matches =
    suggest === null
      ? []
      : symbols
          .filter(
            (s) =>
              !q || s.code.includes(q) || s.name_en.toUpperCase().includes(q),
          )
          .slice(0, 6);

  const recompute = (val: string, caret: number) => {
    setSuggest(tokenAt(val, caret));
    setSel(0);
  };

  const choose = (code: string) => {
    if (!suggest) return;
    const caret = taRef.current?.selectionStart ?? body.length;
    const before = body.slice(0, suggest.start);
    const after = body.slice(caret);
    const next = `${before}$${code} ${after}`;
    setBody(next);
    setSuggest(null);
    const pos = `${before}$${code} `.length;
    requestAnimationFrame(() => {
      const el = taRef.current;
      if (el) {
        el.focus();
        el.setSelectionRange(pos, pos);
      }
    });
  };

  const submit = async () => {
    if (!body.trim()) return;
    setBusy(true);
    setErr("");
    setNotice("");
    try {
      const post = await api.createPost({
        body: body.trim(),
        sentiment,
        parent_id: parentId,
        route_code: routeCode,
      });
      setBody("");
      setSentiment(null);
      setSuggest(null);
      if (post.moderation_status === "pending") {
        setNotice(t("composer.pending"));
      } else {
        onPosted(post);
      }
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail : t("composer.failed"));
    } finally {
      setBusy(false);
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (suggest && matches.length) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSel((i) => (i + 1) % matches.length);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSel((i) => (i - 1 + matches.length) % matches.length);
      } else if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        choose(matches[sel]?.code ?? matches[0].code);
      } else if (e.key === "Escape") {
        e.preventDefault();
        setSuggest(null);
      }
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
      <div className="relative">
        <textarea
          ref={taRef}
          value={body}
          onChange={(e) => {
            setBody(e.target.value);
            recompute(
              e.target.value,
              e.target.selectionStart ?? e.target.value.length,
            );
          }}
          onKeyDown={onKeyDown}
          onClick={(e) =>
            recompute(
              e.currentTarget.value,
              e.currentTarget.selectionStart ?? 0,
            )
          }
          onBlur={() => setTimeout(() => setSuggest(null), 150)}
          placeholder={ph}
          rows={compact ? 2 : 3}
          className="w-full bg-transparent resize-none outline-none text-[15px] placeholder:text-muted"
        />
        {suggest && matches.length > 0 && (
          <div className="absolute left-0 right-0 top-full mt-1 bg-surface border border-border rounded-xl overflow-hidden z-50 shadow-lg">
            {matches.map((s, i) => (
              <button
                key={s.code}
                type="button"
                onMouseDown={(e) => {
                  e.preventDefault();
                  choose(s.code);
                }}
                onMouseEnter={() => setSel(i)}
                className={`w-full text-left px-3 py-2 flex items-center gap-2 ${
                  i === sel ? "bg-card" : "hover:bg-card"
                }`}
              >
                <CompanyLogo code={s.code} size={22} />
                <span className="font-bold text-[13px] text-accent shrink-0">
                  ${s.code}
                </span>
                <span className="text-xs text-muted truncate" lang="bn">
                  {s.name_en}
                  {s.name_bn ? ` · ${s.name_bn}` : ""}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
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
      <p className="text-[11px] text-muted mt-1.5">
        {t("composer.tickerHint")}
      </p>
      {notice && <p className="text-accent text-xs mt-2">{notice}</p>}
      {err && <p className="text-down text-xs mt-2">{err}</p>}
    </div>
  );
}
