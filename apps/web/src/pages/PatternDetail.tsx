import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Link } from "../lib/nav";
import { CompanyLogo } from "../components/CompanyLogo";
import { EvidenceNote } from "../components/EvidenceChip";
import { useSeo } from "../components/Seo";
import { Pct, Spinner, taka } from "../components/ui";
import { api, type PatternStatus, type PatternType, type Screen, type ScreenItem } from "../lib/api";
import { useLang } from "../lib/i18n";
import { getLesson } from "../lib/lessons";
import { PATTERN_LABEL, PATTERN_LESSON_ID, PATTERN_ORDER, patternStatusLabel } from "../lib/patterns";
import { useTenantConfig } from "../lib/tenant";

const VALID_TYPES = new Set<string>(PATTERN_ORDER);

function matchNote(item: ScreenItem, type: PatternType, lang: "bn" | "en"): string | null {
  const status = item.pattern_status as PatternStatus | null | undefined;
  if (!status) return item.note;
  if (type !== "high_volume_flat_base") return patternStatusLabel(status, lang);
  const metrics = item.pattern_metrics ?? {};
  const depth = metrics.base_depth_pct?.toFixed(1) ?? "—";
  if (status === "forming") {
    const distance = metrics.distance_to_breakout_pct?.toFixed(1) ?? "—";
    return lang === "bn"
      ? `রেজিস্ট্যান্সের ${distance}% নিচে · ${depth}% বেস`
      : `${distance}% below resistance · ${depth}% base`;
  }
  const volume = metrics.volume_ratio?.toFixed(1) ?? "—";
  return lang === "bn"
    ? `${volume}x ভলিউমে ব্রেকআউট · ${depth}% বেস`
    : `breakout on ${volume}x volume · ${depth}% base`;
}

// One pattern's plain-language lesson + who's showing it right now on DSE — pairs "what usually
// happens" with a live, checkable answer, rather than leaving the claim untested in the abstract.
export function PatternDetail() {
  const { t, lang } = useLang();
  const { config } = useTenantConfig();
  const { type = "" } = useParams();
  const [screen, setScreen] = useState<Screen | null>(null);

  const validType = VALID_TYPES.has(type) ? (type as PatternType) : null;
  const plabel = validType ? PATTERN_LABEL[validType] : null;
  useSeo({
    noindex: !validType,
    title: plabel
      ? {
          bn: `${plabel.bn} — ${config.exchange_code} চার্ট প্যাটার্ন | ${config.brand_name}`,
          en: `${plabel.en} — ${config.exchange_code} chart pattern | ${config.brand_name}`,
        }
      : undefined,
    description: plabel
      ? {
          bn: validType === "high_volume_flat_base"
            ? `${plabel.bn} সেটআপের কঠোর নিয়ম, ঐতিহাসিক পরীক্ষার সীমা এবং এখন কোন ${config.exchange_code} শেয়ার এটি দেখাচ্ছে। গবেষণার ওয়াচলিস্ট, সংকেত নয়।`
            : `${plabel.bn} প্যাটার্ন কী, সাধারণত এরপর কী হয়, আর এখন কোন ${config.exchange_code} শেয়ার এটি দেখাচ্ছে। প্রথাগত বিশ্লেষণ, পরামর্শ নয়।`,
          en: validType === "high_volume_flat_base"
            ? `Strict ${plabel.en.toLowerCase()} rules, historical test limitations, and which ${config.exchange_code} stocks show it now. Research watchlist, not a signal.`
            : `What a ${plabel.en.toLowerCase()} is, what usually happens next, and which ${config.exchange_code} stocks show it now. Textbook technical analysis, not advice.`,
        }
      : undefined,
  });

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
  const lesson = getLesson(PATTERN_LESSON_ID[patternType], lang, config.market);
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
          <EvidenceNote
            evidence={screen?.evidence ?? (patternType === "high_volume_flat_base" ? "experimental" : "framework")}
          />
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
                {matchNote(it, patternType, lang) && (
                  <div className="mt-0.5 text-[10px] leading-tight text-accent">
                    {matchNote(it, patternType, lang)}
                  </div>
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
