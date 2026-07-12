import { useEffect, useState, type FormEvent } from "react";
import { useSeo } from "../components/Seo";
import { trackProductEvent } from "../lib/analytics";
import { api, ApiError, type InstitutionalLeadInput } from "../lib/api";
import { useLang } from "../lib/i18n";
import { Link } from "../lib/nav";
import { useTenantConfig } from "../lib/tenant";

const EMPTY_FORM: InstitutionalLeadInput = {
  organization: "",
  contact_name: "",
  work_email: "",
  role: "",
  use_case: "",
  source: "institutional_research",
  consent: true,
  website: "",
};

export function Institutions() {
  const { lang } = useLang();
  const { config } = useTenantConfig();
  const bn = lang === "bn";
  const researchBeta = config.research_beta;
  const source = researchBeta ? "research_beta" : "institutional_research";
  const [form, setForm] = useState<InstitutionalLeadInput>(() => ({ ...EMPTY_FORM, source }));
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  const exchange = bn ? config.exchange_name_bn || config.exchange_name : config.exchange_name;

  useSeo({
    title: {
      bn: `${exchange} প্রাতিষ্ঠানিক গবেষণা সাক্ষাৎকার`,
      en: `${exchange} institutional research interviews`,
    },
    description: {
      bn: researchBeta ? "প্রমাণভিত্তিক বাজার গবেষণার সমস্যা বোঝার জন্য সীমিত বেটা সাক্ষাৎকার।" : "প্রমাণভিত্তিক বাজার গবেষণার সমস্যা বোঝার জন্য পেশাজীবীদের সাক্ষাৎকার।",
      en: researchBeta ? "Limited beta interviews to understand evidence-first market research workflows." : "Professional interviews to understand evidence-first market research workflows.",
    },
  });

  useEffect(() => {
    trackProductEvent("view_institutions", { market: config.market, source });
  }, [config.market, source]);

  const update = (key: keyof InstitutionalLeadInput, value: string) =>
    setForm((current) => ({ ...current, [key]: value }));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!consent) return;
    setBusy(true);
    setError("");
    trackProductEvent("submit_institutional_lead", { market: config.market, source });
    try {
      await api.institutionalLead({ ...form, source, consent: true });
      await trackProductEvent("institutional_lead_submitted", {
        market: config.market,
        source,
      });
      setSent(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : bn ? "অনুরোধটি পাঠানো যায়নি।" : "The request could not be sent.");
    } finally {
      setBusy(false);
    }
  };

  const capabilities = bn
    ? [
        ["মনিটরিং", "ঘোষণা, আয়, মালিকানা ও বাজারের অস্বাভাবিক পরিবর্তন এক জায়গায়"],
        ["রিসার্চ অপারেশন", "উৎস, সময় ও প্রমাণসহ পুনরাবৃত্ত কাজ দ্রুত করা"],
        ["ক্লায়েন্ট অভিজ্ঞতা", "ওয়াচলিস্ট ও ব্যাখ্যাযোগ্য বাজার তথ্য নিয়ে ব্যবহারকারীর প্রত্যাশা"],
        [researchBeta ? "বেটা সীমা" : "বর্তমান সীমা", "এই পর্যায়ে API, ডেটা এক্সপোর্ট, SLA বা বাণিজ্যিক সেবা দেওয়া হয় না"],
      ]
    : [
        ["Monitoring", "Disclosures, earnings, ownership and unusual market changes in one place"],
        ["Research operations", "Reduce repetitive work with timestamped, source-linked evidence"],
        ["Client experience", "User expectations around watchlists and explainable market context"],
        [researchBeta ? "Beta boundary" : "Current boundary", "No API, data export, SLA or commercial service is offered at this stage"],
      ];

  return (
    <div className="flex flex-col gap-6">
      <header className="border-b border-border pb-5">
        <div className="text-[10px] font-semibold uppercase tracking-wide text-accent">
          {bn
            ? researchBeta ? "প্রাতিষ্ঠানিক গবেষণা বেটা" : "প্রাতিষ্ঠানিক গবেষণা"
            : researchBeta ? "Institutional research beta" : "Institutional research"}
        </div>
        <h1 className="mt-1 text-2xl font-extrabold leading-tight">
          {bn ? "প্রতিষ্ঠান কীভাবে বাজার গবেষণা করে তা বুঝতে চাই" : "Help us understand institutional research workflows"}
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-muted">
          {bn
            ? `${exchange}-এর ব্রোকার, মার্চেন্ট ব্যাংক, অ্যাসেট ম্যানেজার, গবেষণা দল ও আর্থিক মিডিয়ার পেশাজীবীদের সাথে গবেষণা সাক্ষাৎকার নিচ্ছি। এটি বিক্রয় বা পাইলটের প্রস্তাব নয়।`
            : `We are interviewing ${exchange} professionals at brokers, asset managers, research teams and financial media. This is research, not a sales or pilot offer.`}
        </p>
      </header>

      <section aria-labelledby="capabilities-heading">
        <h2 id="capabilities-heading" className="text-sm font-bold">
          {bn ? "যেখানে মূল্য তৈরি হয়" : "Where the platform creates value"}
        </h2>
        <div className="mt-2 divide-y divide-border border-y border-border">
          {capabilities.map(([title, body]) => (
            <div key={title} className="grid grid-cols-[112px_1fr] gap-3 py-3">
              <div className="text-xs font-bold text-accent">{title}</div>
              <div className="text-xs leading-relaxed text-muted">{body}</div>
            </div>
          ))}
        </div>
      </section>

      <section aria-labelledby="pilot-heading">
        <h2 id="pilot-heading" className="text-sm font-bold">
          {bn ? "এই পর্যায়ে যা হবে" : "What happens at this stage"}
        </h2>
        <p className="mt-1 text-xs leading-relaxed text-muted">
          {bn
            ? "একটি সংক্ষিপ্ত সাক্ষাৎকারে আপনার বর্তমান কাজ, তথ্যের ঘাটতি ও সময়সাপেক্ষ ধাপ বুঝব। কোনো ডেটা, API, SLA বা পেইড সেবা সরবরাহ করা হবে না।"
            : "A short interview covers your current workflow, evidence gaps and repetitive tasks. No data, API, SLA or paid service will be supplied."}
        </p>
      </section>

      <section className="border-t border-border pt-5" aria-labelledby="contact-heading">
        <h2 id="contact-heading" className="text-lg font-bold">
          {bn ? "কাজের সমস্যাটি বলুন" : "Tell us about the workflow"}
        </h2>
        <p className="mt-1 text-xs text-muted">
          {bn ? "উপযুক্ত গবেষণা সাক্ষাৎকারের জন্য আমরা যোগাযোগ করব।" : "We will contact suitable participants for a research interview."}
        </p>

        {sent ? (
          <div className="mt-4 border-y border-up/40 bg-up/10 py-4 text-sm">
            <div className="font-bold text-up">{bn ? "অনুরোধটি গ্রহণ করা হয়েছে" : "Your request has been received"}</div>
            <p className="mt-1 text-xs text-muted">
              {bn ? "আমরা আপনার কাজের ধরন বুঝে যোগাযোগ করব।" : "We will review the use case before contacting you."}
            </p>
          </div>
        ) : (
          <form onSubmit={submit} className="mt-4 flex flex-col gap-3">
            <label className="text-xs font-semibold">
              {bn ? "প্রতিষ্ঠানের নাম" : "Organization"}
              <input required minLength={2} maxLength={160} value={form.organization} onChange={(event) => update("organization", event.target.value)} className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2.5 text-sm font-normal outline-none focus:border-accent" />
            </label>
            <div className="grid grid-cols-2 gap-2">
              <label className="text-xs font-semibold">
                {bn ? "আপনার নাম" : "Your name"}
                <input required minLength={2} maxLength={120} value={form.contact_name} onChange={(event) => update("contact_name", event.target.value)} className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2.5 text-sm font-normal outline-none focus:border-accent" />
              </label>
              <label className="text-xs font-semibold">
                {bn ? "পদবি" : "Role"}
                <input required minLength={2} maxLength={80} value={form.role} onChange={(event) => update("role", event.target.value)} className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2.5 text-sm font-normal outline-none focus:border-accent" />
              </label>
            </div>
            <label className="text-xs font-semibold">
              {bn ? "কাজের ইমেইল" : "Work email"}
              <input required type="email" maxLength={255} value={form.work_email} onChange={(event) => update("work_email", event.target.value)} className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2.5 text-sm font-normal outline-none focus:border-accent" />
            </label>
            <label className="text-xs font-semibold">
              {bn ? "কোন কাজটি উন্নত করতে চান?" : "Which workflow should improve?"}
              <textarea required minLength={20} maxLength={1200} rows={5} value={form.use_case} onChange={(event) => update("use_case", event.target.value)} className="mt-1 w-full resize-y rounded-lg border border-border bg-surface px-3 py-2.5 text-sm font-normal leading-relaxed outline-none focus:border-accent" />
            </label>
            <label className="sr-only" aria-hidden="true">
              Website
              <input tabIndex={-1} autoComplete="off" value={form.website} onChange={(event) => update("website", event.target.value)} />
            </label>
            <label className="flex items-start gap-2 text-[11px] leading-relaxed text-muted">
              <input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} className="mt-0.5 h-4 w-4 accent-[var(--color-accent)]" />
              <span>
                {bn ? "এই অনুরোধ সম্পর্কে আমার সাথে যোগাযোগ করতে সম্মতি দিচ্ছি এবং " : "I agree to be contacted about this request and accept the "}
                <Link to="/privacy" className="text-accent">{bn ? "গোপনীয়তা নীতি" : "privacy policy"}</Link>.
              </span>
            </label>
            {error && <p className="text-xs text-down">{error}</p>}
            <button type="submit" disabled={busy || !consent} className="rounded-lg bg-accent py-3 text-sm font-bold text-bg disabled:opacity-40">
              {busy ? "…" : bn ? "গবেষণা সাক্ষাৎকারে আগ্রহ জানান" : "Volunteer for an interview"}
            </button>
          </form>
        )}
      </section>

      <p className="text-[10px] leading-relaxed text-muted">
        {bn ? "ভবিষ্যতে কোনো বাণিজ্যিক পাইলট বিবেচনার আগে আইনগত অবস্থা, ডেটা ব্যবহারের অধিকার, নিরাপত্তা, সহায়তা ও সেবার সীমা আলাদাভাবে যাচাই ও লিখিতভাবে নির্ধারণ করা হবে।" : "Any future commercial pilot would require separate legal and data-rights clearance plus written security, support and service boundaries."}
      </p>
    </div>
  );
}
