import { useEffect, useRef, useState } from "react";
import { useLang } from "../lib/i18n";
import { LearnSheet } from "./LearnSheet";

// A small tap-to-toggle "(i)" popover for explaining a widget's metric in plain language.
// Tap (not hover) so it works on touch/PWA; closes on outside tap. Resets header text styling
// (uppercase/tracking) so the explanation reads as normal prose. With a lessonId, the popover also
// offers "Learn how to use it →", opening a worked-example lesson sheet.
export function InfoTip({ text, lessonId }: { text: string; lessonId?: string }) {
  const { t } = useLang();
  const [open, setOpen] = useState(false);
  const [learn, setLearn] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  return (
    <span ref={ref} className="relative inline-flex align-middle">
      <button
        type="button"
        aria-label={t("infoTip.aria")}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        className="w-4 h-4 grid place-items-center rounded-full border border-border text-[10px] font-semibold leading-none text-muted hover:text-accent hover:border-accent"
      >
        i
      </button>
      {open && (
        <span className="absolute left-0 top-6 z-30 w-60 rounded-lg border border-border bg-card p-2.5 text-[11px] font-normal normal-case tracking-normal leading-snug text-fg shadow-lg">
          {text}
          {lessonId && (
            <button
              type="button"
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                setOpen(false);
                setLearn(true);
              }}
              className="block mt-2 text-accent font-semibold"
            >
              {t("infoTip.learn")}
            </button>
          )}
        </span>
      )}
      {learn && lessonId && <LearnSheet lessonId={lessonId} onClose={() => setLearn(false)} />}
    </span>
  );
}
