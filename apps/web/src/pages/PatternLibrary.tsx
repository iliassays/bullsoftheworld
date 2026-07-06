import { useEffect, useState } from "react";
import { Link } from "../lib/nav";
import { EvidenceNote } from "../components/EvidenceChip";
import { useSeo } from "../components/Seo";
import { Spinner } from "../components/ui";
import { api, type ScreensResponse } from "../lib/api";
import { useLang } from "../lib/i18n";
import { PATTERN_LABEL, PATTERN_ORDER } from "../lib/patterns";

// Index of every chart pattern this site detects — "what is it, and who's showing it right now."
// One board per shape (chart_pattern_<type>), not a single combined list — a user asked for this
// split so each pattern reads as its own thing. Framework evidence throughout: classic technical
// analysis, not proven on DSE (see each pattern's lesson for the full reasoning).
export function PatternLibrary() {
  const { t, lang } = useLang();
  useSeo({
    title: {
      bn: "চার্ট প্যাটার্ন — DSE শেয়ারে ত্রিভুজ, চ্যানেল, ডাবল টপ/বটম | Bulls of Dhaka",
      en: "Chart patterns — triangles, channels, double tops/bottoms on DSE | Bulls of Dhaka",
    },
    description: {
      bn: "ঢাকা স্টক এক্সচেঞ্জের শেয়ারে গঠিত হওয়া ক্লাসিক চার্ট প্যাটার্ন — প্রতিটি প্যাটার্নের মানে ও এখন কোন শেয়ার দেখাচ্ছে। প্রথাগত টেকনিক্যাল অ্যানালাইসিস, পরামর্শ নয়।",
      en: "Classic chart patterns forming on Dhaka Stock Exchange stocks — what each means and which stocks show it now. Textbook technical analysis, not advice.",
    },
  });
  const [data, setData] = useState<ScreensResponse | null>(null);

  useEffect(() => {
    api
      .screens()
      .then(setData)
      .catch(() => setData(null));
  }, []);

  const byKey = new Map((data?.screens ?? []).map((s) => [s.key, s]));
  const counts: Record<string, number> = {};
  for (const type of PATTERN_ORDER) {
    counts[type] = byKey.get(`chart_pattern_${type}`)?.items.length ?? 0;
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

      {data === null ? (
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
