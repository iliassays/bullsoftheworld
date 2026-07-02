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
    en: "We tested this pattern against 2 years of real DSE price history and it showed a genuine edge there. Past results never guarantee the future.",
    bn: "এই প্যাটার্নটি আমরা DSE-র ২ বছরের আসল দামের ইতিহাসে পরীক্ষা করেছি — সেখানে সত্যিকারের এজ দেখা গেছে। অতীতের ফল কখনোই ভবিষ্যতের নিশ্চয়তা নয়।",
  },
  framework: {
    en: "A classic investing method (Buffett/Graham style). Sensible thinking — but we have not separately proven it on DSE data.",
    bn: "ক্লাসিক বিনিয়োগ পদ্ধতি (Buffett/Graham ধাঁচের)। যুক্তিসঙ্গত চিন্তা — তবে DSE-র ডেটায় আলাদাভাবে প্রমাণিত নয়।",
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
