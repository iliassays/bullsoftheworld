import { useEffect, useState } from "react";
import { useLang } from "../lib/i18n";
import { Link } from "../lib/nav";

// Google Consent Mode (index.html) already defaults analytics/ad storage to "denied" for the
// EEA + UK — decided by Google's own geo-IP, not by us. This banner is just the opt-in surface for
// visitors in that region: skipped entirely everywhere else (including Bangladesh), matching the
// zero-friction default for that audience. The timezone check is a best-effort proxy for "show the
// banner" only; it never weakens the actual region-scoped default in index.html.
const CONSENT_KEY = "bulls.euConsent.v1";

function looksEuropean(): boolean {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone?.startsWith("Europe/") ?? false;
  } catch {
    return false;
  }
}

function updateConsent(granted: boolean) {
  const w = window as typeof window & { gtag?: (...args: unknown[]) => void };
  w.gtag?.("consent", "update", {
    ad_storage: granted ? "granted" : "denied",
    analytics_storage: granted ? "granted" : "denied",
  });
}

export function EuConsentGate() {
  const { lang } = useLang();
  const bn = lang === "bn";
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (localStorage.getItem(CONSENT_KEY)) return;
    if (looksEuropean()) setVisible(true);
  }, []);

  if (!visible) return null;

  const decide = (granted: boolean) => {
    localStorage.setItem(CONSENT_KEY, granted ? "granted" : "denied");
    updateConsent(granted);
    setVisible(false);
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="eu-consent-title"
      className="fixed inset-x-0 bottom-0 z-50 mx-auto max-w-[480px] border-t border-border bg-nav px-4 pb-[calc(1rem+env(safe-area-inset-bottom))] pt-4 shadow-2xl"
    >
      <h2 id="eu-consent-title" className="text-sm font-bold">
        {bn ? "অ্যানালিটিক্স অনুমতি" : "Analytics consent"}
      </h2>
      <p className="mt-1 text-xs leading-relaxed text-muted">
        {bn
          ? "EU/UK দর্শকদের জন্য আইন অনুযায়ী, আমরা আপনার অনুমতি ছাড়া Google Analytics চালু করি না। বাকি সব জায়গায় এটি স্বয়ংক্রিয়ভাবে চলে।"
          : "For EU/UK visitors we don't run Google Analytics without your say-so, as required by law. Everywhere else it runs automatically."}
      </p>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <button
          type="button"
          onClick={() => decide(false)}
          className="min-h-10 rounded-lg border border-border px-3 text-xs font-semibold"
        >
          {bn ? "প্রত্যাখ্যান" : "Reject"}
        </button>
        <button
          type="button"
          onClick={() => decide(true)}
          className="min-h-10 rounded-lg bg-accent px-3 text-xs font-bold text-bg"
        >
          {bn ? "অনুমতি দিন" : "Allow"}
        </button>
      </div>
      <p className="mt-2 text-center text-[10px] text-muted">
        <Link to="/privacy" className="text-accent">
          {bn ? "গোপনীয়তার বিস্তারিত" : "Privacy details"}
        </Link>
      </p>
    </div>
  );
}
