import { createContext, useContext, useState, type ReactNode } from "react";
import {
  readAnalyticsConsent,
  writeAnalyticsConsent,
  type AnalyticsConsent,
} from "../lib/consent";
import { useLang } from "../lib/i18n";
import { Link } from "../lib/nav";
import { useTenantConfig } from "../lib/tenant";

interface ConsentContextValue {
  analytics: AnalyticsConsent;
  openSettings: () => void;
}

const ConsentContext = createContext<ConsentContextValue>({
  analytics: "unknown",
  openSettings: () => undefined,
});

export function ConsentProvider({ children }: { children: ReactNode }) {
  const [analytics, setAnalytics] = useState<AnalyticsConsent>(readAnalyticsConsent);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const decide = (value: Exclude<AnalyticsConsent, "unknown">) => {
    writeAnalyticsConsent(value);
    setAnalytics(value);
    setSettingsOpen(false);
  };

  return (
    <ConsentContext.Provider value={{ analytics, openSettings: () => setSettingsOpen(true) }}>
      {children}
      <ConsentBanner
        visible={analytics === "unknown" || settingsOpen}
        current={analytics}
        onDecide={decide}
        onClose={() => setSettingsOpen(false)}
      />
    </ConsentContext.Provider>
  );
}

export function useConsent(): ConsentContextValue {
  return useContext(ConsentContext);
}

function ConsentBanner({
  visible,
  current,
  onDecide,
  onClose,
}: {
  visible: boolean;
  current: AnalyticsConsent;
  onDecide: (value: "granted" | "denied") => void;
  onClose: () => void;
}) {
  const { lang } = useLang();
  const { config } = useTenantConfig();
  const bn = lang === "bn";
  if (!visible) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="consent-title"
      className="fixed inset-x-0 bottom-0 z-50 mx-auto max-w-[480px] border-t border-border bg-nav px-4 pb-[calc(1rem+env(safe-area-inset-bottom))] pt-4 shadow-2xl"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 id="consent-title" className="text-sm font-bold">
            {bn ? "ঐচ্ছিক অ্যানালিটিক্স" : "Optional analytics"}
          </h2>
          <p className="mt-1 text-xs leading-relaxed text-muted">
            {bn
              ? `লগইন, ভাষা ও ওয়াচলিস্টের জন্য প্রয়োজনীয় স্টোরেজ চালু থাকে। আপনার অনুমতি পেলে শুধু আমাদের সার্ভারে ছদ্মনামযুক্ত ব্যবহার তথ্য রাখা হবে। ${config.research_beta ? "এই বেটায়" : "এই সেবায়"} Google Analytics বা বিজ্ঞাপনের ট্র্যাকার নেই।`
              : `Essential storage keeps login, language and watchlists working. If allowed, pseudonymous usage data stays on our service. ${config.research_beta ? "This beta" : "This service"} runs no Google Analytics or advertising trackers.`}
          </p>
        </div>
        {current !== "unknown" && (
          <button type="button" onClick={onClose} aria-label={bn ? "বন্ধ করুন" : "Close"} className="text-lg leading-none text-muted">
            ×
          </button>
        )}
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <button type="button" onClick={() => onDecide("denied")} className="min-h-10 rounded-lg border border-border px-3 text-xs font-semibold">
          {bn ? "ঐচ্ছিক অংশ প্রত্যাখ্যান" : "Reject optional"}
        </button>
        <button type="button" onClick={() => onDecide("granted")} className="min-h-10 rounded-lg bg-accent px-3 text-xs font-bold text-bg">
          {bn ? "অ্যানালিটিক্স অনুমতি দিন" : "Allow analytics"}
        </button>
      </div>
      <p className="mt-2 text-center text-[10px] text-muted">
        <Link to="/privacy" className="text-accent">{bn ? "গোপনীয়তার বিস্তারিত" : "Privacy details"}</Link>
      </p>
    </div>
  );
}
