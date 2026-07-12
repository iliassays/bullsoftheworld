import { useMemo, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { useSeo } from "../components/Seo";
import { api, ApiError, type BetaFeedbackInput, type BetaFeedbackKind } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useLang } from "../lib/i18n";
import { Link } from "../lib/nav";
import { useTenantConfig } from "../lib/tenant";

const KINDS: Array<{ value: BetaFeedbackKind; en: string; bn: string }> = [
  { value: "useful", en: "Useful", bn: "উপকারী" },
  { value: "unclear", en: "Unclear", bn: "অস্পষ্ট" },
  { value: "incorrect", en: "Looks incorrect", bn: "ভুল মনে হচ্ছে" },
  { value: "missing", en: "Something is missing", bn: "কিছু অনুপস্থিত" },
  { value: "other", en: "Other", bn: "অন্য কিছু" },
];

function safeSource(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return "/";
  return raw.slice(0, 512);
}

function symbolFromPath(path: string): string | null {
  const match = path.match(/^\/(?:bn|en)\/s\/([A-Za-z0-9.\-]{1,32})(?:[/?]|$)/);
  return match ? match[1].toUpperCase() : null;
}

export function Beta() {
  const { lang } = useLang();
  const { config } = useTenantConfig();
  const { user } = useAuth();
  const [params] = useSearchParams();
  const bn = lang === "bn";
  const sourcePath = useMemo(() => safeSource(params.get("from")), [params]);
  const symbolCode = useMemo(() => symbolFromPath(sourcePath), [sourcePath]);
  const [kind, setKind] = useState<BetaFeedbackKind>("useful");
  const [message, setMessage] = useState("");
  const [contactConsent, setContactConsent] = useState(false);
  const [website, setWebsite] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  useSeo({
    title: { bn: `রিসার্চ বেটা — ${config.brand_name}`, en: `Research beta — ${config.brand_name}` },
    noindex: true,
  });

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    const body: BetaFeedbackInput = {
      kind,
      message,
      path: sourcePath,
      symbol_code: symbolCode,
      contact_consent: Boolean(user && contactConsent),
      website,
    };
    try {
      await api.betaFeedback(body);
      setSent(true);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail : bn ? "পাঠানো যায়নি। আবার চেষ্টা করুন।" : "Could not send feedback. Try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <header className="border-b border-border pb-4">
        <div className="text-[10px] font-semibold uppercase tracking-wide text-accent">
          {bn ? "সীমিত গবেষণা পর্যায়" : "Limited research phase"}
        </div>
        <h1 className="mt-1 text-2xl font-extrabold">{bn ? "রিসার্চ বেটা" : "Research beta"}</h1>
        <p className="mt-2 text-sm leading-relaxed text-muted">
          {bn
            ? "এই বিনামূল্যের বেটায় আমরা যাচাই করছি তথ্যগুলো বিনিয়োগকারীদের গবেষণায় সত্যিই সময় বাঁচায় কি না। এটি কোনো বাণিজ্যিক রিসার্চ সেবা নয়।"
            : "This free beta tests whether the evidence genuinely saves investors research time. It is not a commercially offered research service."}
        </p>
      </header>

      <section className="divide-y divide-border border-y border-border">
        {[
          bn ? "তথ্য বিলম্বিত, অসম্পূর্ণ বা ভুল হতে পারে।" : "Data may be delayed, incomplete or wrong.",
          bn ? "কোনো স্কোর, আইডিয়া বা সারাংশ কেনা-বেচার পরামর্শ নয়।" : "No score, idea or summary is a buy or sell recommendation.",
          bn ? "বেটায় বিজ্ঞাপন, পেইড সাবস্ক্রিপশন বা প্রাতিষ্ঠানিক ডেটা সরবরাহ নেই।" : "The beta has no ads, paid subscriptions or institutional data delivery.",
          bn ? "গুরুত্বপূর্ণ সিদ্ধান্তের আগে মূল উৎস ও সময় যাচাই করুন।" : "Check the primary source and timestamp before an important decision.",
        ].map((item) => (
          <p key={item} className="py-3 text-xs leading-relaxed text-muted">{item}</p>
        ))}
      </section>

      <section>
        <h2 className="text-base font-bold">{bn ? "এই পৃষ্ঠাটি কেমন কাজ করেছে?" : "How did this page work for you?"}</h2>
        <p className="mt-1 text-xs text-muted">
          {bn ? `যে পৃষ্ঠা থেকে এসেছেন: ${sourcePath}` : `Page being reviewed: ${sourcePath}`}
        </p>
        {sent ? (
          <div className="mt-4 border-y border-up/40 bg-up/10 py-4 text-sm text-up">
            {bn ? "ধন্যবাদ। আপনার মতামত বেটা পর্যালোচনায় যোগ হয়েছে।" : "Thank you. Your feedback is now in the beta review queue."}
          </div>
        ) : (
          <form onSubmit={submit} className="mt-4 flex flex-col gap-3">
            <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label={bn ? "মতামতের ধরন" : "Feedback type"}>
              {KINDS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  role="radio"
                  aria-checked={kind === option.value}
                  onClick={() => setKind(option.value)}
                  className={`min-h-11 rounded-lg border px-3 text-xs font-semibold ${kind === option.value ? "border-accent bg-accent/10 text-accent" : "border-border bg-surface text-text"}`}
                >
                  {bn ? option.bn : option.en}
                </button>
              ))}
            </div>
            <label className="text-xs font-semibold">
              {kind === "useful"
                ? bn ? "আরও কিছু বলতে চান? (ঐচ্ছিক)" : "Anything else? (optional)"
                : bn ? "কী দেখেছেন?" : "What did you notice?"}
              <textarea
                value={message}
                onChange={(event) => setMessage(event.target.value)}
                required={kind !== "useful"}
                minLength={kind === "useful" ? undefined : 10}
                maxLength={1200}
                rows={5}
                className="mt-1 w-full resize-y rounded-lg border border-border bg-surface px-3 py-2.5 text-sm font-normal leading-relaxed outline-none focus:border-accent"
              />
            </label>
            <label className="sr-only" aria-hidden="true">
              Website
              <input tabIndex={-1} autoComplete="off" value={website} onChange={(event) => setWebsite(event.target.value)} />
            </label>
            {user ? (
              <label className="flex items-start gap-2 text-[11px] leading-relaxed text-muted">
                <input type="checkbox" checked={contactConsent} onChange={(event) => setContactConsent(event.target.checked)} className="mt-0.5 h-4 w-4 accent-[var(--color-accent)]" />
                <span>{bn ? "এই মতামত সম্পর্কে আমার অ্যাকাউন্টের যোগাযোগ ঠিকানায় উত্তর দিতে পারেন।" : "You may contact me through my account about this feedback."}</span>
              </label>
            ) : (
              <p className="text-[11px] leading-relaxed text-muted">
                {bn ? "মতামতটি নাম ছাড়া সংরক্ষিত হবে। উত্তর চাইলে আগে " : "This feedback will be stored without your identity. To allow a reply, "}
                <Link to={`/me?mode=register&next=${encodeURIComponent(`/beta?from=${sourcePath}`)}`} className="text-accent">
                  {bn ? "লগইন করুন" : "sign in first"}
                </Link>.
              </p>
            )}
            {error && <p className="text-xs text-down">{error}</p>}
            <button type="submit" disabled={busy} className="min-h-11 rounded-lg bg-accent px-3 text-sm font-bold text-bg disabled:opacity-40">
              {busy ? "…" : bn ? "মতামত পাঠান" : "Send feedback"}
            </button>
          </form>
        )}
      </section>

      <p className="text-[10px] leading-relaxed text-muted">
        {bn ? "তথ্য সংশোধনের অনুরোধ অগ্রাধিকার পায়। ব্যক্তিগত আর্থিক বা ব্রোকার তথ্য লিখবেন না।" : "Correction reports are prioritized. Do not include personal financial or broker information."}
      </p>
    </div>
  );
}
