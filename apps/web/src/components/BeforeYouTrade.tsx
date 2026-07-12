import { useState } from "react";
import { useLang } from "../lib/i18n";
import { useTenantConfig } from "../lib/tenant";

// A descriptive decision *process* — not a verdict. Collapsed by default so it never nags; a trader
// can open it at the moment of deciding. Teaches a repeatable habit without ever saying buy/sell.
const STEPS_EN: { q: string; why: string; dseOnly?: boolean }[] = [
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
    why: "Thinly traded or suspended names can be hard to exit. Compare your order with normal traded value.",
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

const STEPS_BN: typeof STEPS_EN = [
  {
    q: "দাম কেন নড়ছে?",
    why: "আগে খবর ও অফিশিয়াল ঘোষণা দেখুন। বাস্তব খবরের মুভ আর কারণহীন মুভ এক নয়।",
  },
  {
    q: "ট্রেন্ড কি আপনার পক্ষে?",
    why: "সাপোর্টের কাছে প্রবেশ আর ইতিমধ্যে দ্রুত বেড়ে যাওয়া দাম ধাওয়া করা এক ধরনের ঝুঁকি নয়।",
  },
  {
    q: "প্রয়োজনে বের হতে পারবেন?",
    why: "কম লেনদেন বা স্থগিত শেয়ার থেকে বের হওয়া কঠিন হতে পারে। স্বাভাবিক লেনদেনের তুলনায় অর্ডারের আকার দেখুন।",
  },
  {
    q: "কেনার আগেই পরিকল্পনা কী?",
    why: "প্রবেশের দাম, লক্ষ্য এবং কোন দামে আপনার ধারণা ভুল প্রমাণিত হবে তা আগে ঠিক করুন।",
  },
  {
    q: "অর্ডারের আকার কি যুক্তিসঙ্গত?",
    why: "একটি ট্রেড যেন বড় ক্ষতি করতে না পারে। হারাতে পারবেন এমন টাকার মধ্যেই ঝুঁকি নিন।",
  },
];

export function BeforeYouTrade() {
  const { lang } = useLang();
  const { config } = useTenantConfig();
  const bn = lang === "bn";
  const steps = bn ? STEPS_BN : STEPS_EN;
  const [open, setOpen] = useState(false);
  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between font-semibold text-sm"
      >
        <span>✅ {bn ? "ট্রেডের আগে" : "Before you trade"}</span>
        <span className="text-muted">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <>
          <ul className="mt-3 flex flex-col gap-2.5">
            {steps.map((s, i) => (
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
            {bn
              ? "সিদ্ধান্তটি ভেবে দেখার চেকলিস্ট — কোনো সুপারিশ নয়। সিদ্ধান্ত ও ঝুঁকি আপনার।"
              : `A checklist for ${config.exchange_code} research, not a recommendation. The decision and risk are yours.`}
          </p>
        </>
      )}
    </div>
  );
}
