import { useState } from "react";
import { type Lang, useLang } from "../lib/i18n";

// Truth-in-labeling chip: what kind of evidence stands behind a board, in plain words.
// Tapping it opens the one-sentence explanation — nobody should have to guess.
const EVIDENCE_TEXT: Record<string, Record<Lang, string>> = {
  backtested: { en: "🧪 tested on history", bn: "🧪 ইতিহাসে যাচাইকৃত" },
  framework: { en: "📐 classic method", bn: "📐 ক্লাসিক পদ্ধতি" },
  utility: { en: "🔧 info list", bn: "🔧 তথ্যের তালিকা" },
};

const EVIDENCE_EXPLAIN: Record<string, Record<Lang, string>> = {
  backtested: {
    en: "This showed a historical result in two years of DSE data covering one observed market regime. It has not been independently validated or proven in live trading.",
    bn: "DSE-র দুই বছরের একটি পর্যবেক্ষিত বাজার-পর্বে এটি ঐতিহাসিক ফল দেখিয়েছে। স্বাধীনভাবে যাচাই বা লাইভ ট্রেডিংয়ে প্রমাণ করা হয়নি।",
  },
  framework: {
    en: "A classic, widely-used method (e.g. Buffett/Graham-style value investing, or textbook chart-pattern reading). Sensible thinking — but we have not separately proven it on DSE data.",
    bn: "একটি ক্লাসিক, ব্যাপক-ব্যবহৃত পদ্ধতি (যেমন Buffett/Graham ধাঁচের ভ্যালু বিনিয়োগ, বা প্রথাগত চার্ট-প্যাটার্ন পাঠ)। যুক্তিসঙ্গত চিন্তা — তবে DSE-র ডেটায় আলাদাভাবে প্রমাণিত নয়।",
  },
  utility: {
    en: "A useful information list — it makes no claim of predicting anything.",
    bn: "দরকারি তথ্যের তালিকা — এটি কোনো ভবিষ্যদ্বাণীর দাবি করে না।",
  },
};

export function evidenceExplain(evidence: string, lang: Lang): string | undefined {
  return EVIDENCE_EXPLAIN[evidence]?.[lang];
}

export function EvidenceChip({
  evidence,
  onToggle,
}: {
  evidence?: string | null;
  onToggle?: () => void;
}) {
  const { lang } = useLang();
  const text = evidence ? EVIDENCE_TEXT[evidence]?.[lang] : null;
  if (!text) return null;
  const tone =
    evidence === "backtested"
      ? "border-up/40 bg-up/10 text-up"
      : "border-border bg-card text-muted";
  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        onToggle?.();
      }}
      className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${tone}`}
    >
      {text}
    </button>
  );
}

// Chip + tap-to-expand explanation in one drop-in block, with an optional board-specific
// extra note (e.g. the momentum-family caution).
export function EvidenceNote({
  evidence,
  extra,
}: {
  evidence?: string | null;
  extra?: string;
}) {
  const { lang } = useLang();
  const [open, setOpen] = useState(false);
  if (!evidence) return null;
  return (
    <>
      <EvidenceChip evidence={evidence} onToggle={() => setOpen((v) => !v)} />
      {open && (
        <p
          lang={lang}
          className="basis-full mt-1.5 rounded-xl bg-card/60 border border-border p-2.5 text-[11px] leading-relaxed text-muted"
        >
          {evidenceExplain(evidence, lang)}
          {extra ? ` ${extra}` : ""}
        </p>
      )}
    </>
  );
}
