import { useState } from "react";

// A descriptive decision *process* — not a verdict. Collapsed by default so it never nags; a trader
// can open it at the moment of deciding. Teaches a repeatable habit without ever saying buy/sell.
const STEPS: { q: string; why: string }[] = [
  {
    q: "Why is it moving?",
    why: "Check the news / announcements first. A jump on real news is different from a jump on nothing.",
  },
  {
    q: "Is the trend with you?",
    why: "Buying near a support level is a different bet from chasing a stock that already spiked.",
  },
  {
    q: "Can you actually get out?",
    why: "Thinly-traded, Z-category or suspended names are hard to exit — size down or skip.",
  },
  {
    q: "What's your plan — before you buy?",
    why: "Decide your entry, a target, and the price where you'd admit you're wrong (your exit).",
  },
  {
    q: "Is the size sensible?",
    why: "No single trade should be able to hurt you badly. Risk only what you can lose.",
  },
];

export function BeforeYouTrade() {
  const [open, setOpen] = useState(false);
  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between text-accent font-semibold text-sm"
      >
        <span>✅ Before you trade</span>
        <span className="text-muted">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <>
          <ul className="mt-3 flex flex-col gap-2.5">
            {STEPS.map((s, i) => (
              <li key={i} className="flex gap-2">
                <span className="text-[11px] text-muted tnum mt-0.5">{i + 1}</span>
                <span>
                  <span className="text-[13px] font-semibold block leading-snug">{s.q}</span>
                  <span className="text-[12px] text-muted leading-snug">{s.why}</span>
                </span>
              </li>
            ))}
          </ul>
          <p className="text-[10px] text-muted mt-3">
            A checklist to think it through — not a recommendation. The decision and the risk are
            yours.
          </p>
        </>
      )}
    </div>
  );
}
