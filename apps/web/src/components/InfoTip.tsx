import { useEffect, useRef, useState } from "react";

// A small tap-to-toggle "(i)" popover for explaining a widget's metric in plain language.
// Tap (not hover) so it works on touch/PWA; closes on outside tap. Resets header text styling
// (uppercase/tracking) so the explanation reads as normal prose.
export function InfoTip({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
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
        aria-label="What is this?"
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
        </span>
      )}
    </span>
  );
}
