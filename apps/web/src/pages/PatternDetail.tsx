import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { CompanyLogo } from "../components/CompanyLogo";
import { EvidenceNote } from "../components/EvidenceChip";
import { Pct, Spinner, taka } from "../components/ui";
import { api, type PatternType, type Screen } from "../lib/api";
import { useLang } from "../lib/i18n";
import { getLesson } from "../lib/lessons";
import { PATTERN_LABEL, PATTERN_LESSON_ID, PATTERN_ORDER } from "../lib/patterns";

const VALID_TYPES = new Set<string>(PATTERN_ORDER);

// One pattern's plain-language lesson + who's showing it right now on DSE — pairs "what usually
// happens" with a live, checkable answer, rather than leaving the claim untested in the abstract.
export function PatternDetail() {
  const { t, lang } = useLang();
  const { type = "" } = useParams();
  const [screen, setScreen] = useState<Screen | null>(null);

  useEffect(() => {
    if (!VALID_TYPES.has(type)) return;
    setScreen(null);
    api
      .screen(`chart_pattern_${type}`, 200)
      .then(setScreen)
      .catch(() => setScreen(null));
  }, [type]);

  if (!VALID_TYPES.has(type)) {
    return (
      <div className="flex flex-col gap-3">
        <Link to="/learn/patterns" className="text-xs text-accent px-1">
          {t("backToPatterns")}
        </Link>
        <p className="text-sm text-muted px-1">{t("patterns.unknown")}</p>
      </div>
    );
  }
  const patternType = type as PatternType;
  const lesson = getLesson(PATTERN_LESSON_ID[patternType], lang);
  const rows: { label: string; body: string }[] = lesson
    ? [
        { label: t("learn.what"), body: lesson.what },
        { label: t("learn.use"), body: lesson.use },
        { label: t("learn.watch"), body: lesson.watch },
        { label: t("learn.example"), body: lesson.example },
      ]
    : [];

  const matches = screen?.items ?? [];

  return (
    <div className="flex flex-col gap-3">
      <Link to="/learn/patterns" className="text-xs text-accent px-1">
        {t("backToPatterns")}
      </Link>
      <div className="px-1">
        <div className="font-bold text-lg">
          {lang === "bn" ? PATTERN_LABEL[patternType].bn : PATTERN_LABEL[patternType].en}
        </div>
        <div className="mt-2">
          <EvidenceNote evidence="framework" />
        </div>
      </div>

      <div className="bg-surface border border-border rounded-2xl p-4 flex flex-col gap-3">
        {rows.map((r) => (
          <div key={r.label}>
            <div className="text-[11px] uppercase tracking-wide text-muted">{r.label}</div>
            <p className="text-[13px] leading-snug mt-0.5">{r.body}</p>
          </div>
        ))}
      </div>

      <div className="px-1 text-[11px] uppercase tracking-wide text-muted mt-1">
        {t("patterns.showingNow")}
      </div>
      {screen === null ? (
        <Spinner />
      ) : matches.length === 0 ? (
        <p className="text-sm text-muted px-1">{t("patterns.showingNone")}</p>
      ) : (
        <div className="flex flex-col divide-y divide-border bg-surface border border-border rounded-2xl">
          {matches.map((it) => (
            <Link
              key={it.code}
              to={`/s/${it.code}`}
              className="flex items-center gap-2.5 p-3"
            >
              <CompanyLogo code={it.code} size={28} />
              <div className="flex-1 min-w-0">
                <div className="font-bold text-[13px]">${it.code}</div>
                {it.name && it.name !== it.code && (
                  <div className="text-[11px] text-muted truncate">{it.name}</div>
                )}
              </div>
              <div className="text-right">
                <div className="text-xs tnum">{taka(it.last_close)}</div>
                {it.change_1d != null && <Pct value={it.change_1d} />}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
