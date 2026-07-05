import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { EvidenceNote } from "../components/EvidenceChip";
import { Spinner } from "../components/ui";
import { api, type Screen } from "../lib/api";
import { useLang } from "../lib/i18n";
import { PATTERN_LABEL, PATTERN_ORDER, patternTypeFromNote } from "../lib/patterns";

// Index of every chart pattern this site detects — "what is it, and who's showing it right now."
// Framework evidence throughout: classic technical analysis, not proven on DSE (see the
// chart_patterns screen's description and each pattern's lesson for the full reasoning).
export function PatternLibrary() {
  const { t, lang } = useLang();
  const [screen, setScreen] = useState<Screen | null>(null);

  useEffect(() => {
    api
      .screen("chart_patterns", 200)
      .then(setScreen)
      .catch(() => setScreen(null));
  }, []);

  const counts: Record<string, number> = {};
  for (const item of screen?.items ?? []) {
    const type = patternTypeFromNote(item.note);
    if (type) counts[type] = (counts[type] ?? 0) + 1;
  }

  return (
    <div className="flex flex-col gap-3">
      <Link to="/markets" className="text-xs text-accent px-1">
        {t("backToMarkets")}
      </Link>
      <div className="px-1">
        <div className="flex items-center gap-2">
          <span aria-hidden>📐</span>
          <div className="font-bold text-lg">{t("patterns.title")}</div>
        </div>
        <p className="text-[12px] text-muted mt-1 leading-relaxed">{t("patterns.intro")}</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          <EvidenceNote evidence="framework" />
        </div>
      </div>

      {screen === null ? (
        <Spinner />
      ) : (
        <div className="flex flex-col gap-2">
          {PATTERN_ORDER.map((type) => (
            <Link
              key={type}
              to={`/learn/patterns/${type}`}
              className="flex items-center justify-between bg-surface border border-border rounded-2xl p-3.5"
            >
              <div>
                <div className="font-semibold text-sm">
                  {lang === "bn" ? PATTERN_LABEL[type].bn : PATTERN_LABEL[type].en}
                </div>
                <div className="text-[11px] text-muted mt-0.5">
                  {counts[type]
                    ? t("patterns.showingCount").replace("{n}", String(counts[type]))
                    : t("patterns.showingNone")}
                </div>
              </div>
              <span className="text-accent text-lg" aria-hidden>
                →
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
