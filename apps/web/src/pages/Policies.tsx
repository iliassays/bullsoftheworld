import { useSeo } from "../components/Seo";
import { useLang } from "../lib/i18n";
import { useTenantConfig } from "../lib/tenant";

function PolicyPage({ kind }: { kind: "privacy" | "terms" }) {
  const { lang } = useLang();
  const { config } = useTenantConfig();
  const bn = lang === "bn";
  const privacy = kind === "privacy";
  const researchBeta = config.research_beta;
  const title = privacy
    ? bn ? "গোপনীয়তা নীতি" : "Privacy policy"
    : bn ? "ব্যবহারের শর্তাবলি" : "Terms of use";
  useSeo({
    title: { bn: `${title} — ${config.brand_name}`, en: `${title} — ${config.brand_name}` },
    description: {
      bn: `${config.brand_name}-এর ${title}।`,
      en: `${config.brand_name} ${title.toLowerCase()}.`,
    },
  });

  const privacySections = bn
    ? [
        ["আমরা যা সংগ্রহ করি", `অ্যাকাউন্ট খুললে নাম, ইমেইল বা ফোন এবং নিরাপদ পাসওয়ার্ড হ্যাশ রাখা হয়। আপনি যোগ করলে ওয়াচলিস্ট, অ্যালার্ট, ম্যানুয়াল পোর্টফোলিও ও কমিউনিটি কনটেন্ট রাখা হয়। গবেষণা সাক্ষাৎকারের ফর্মে দেওয়া যোগাযোগের তথ্য এবং ${researchBeta ? "বেটা ফিডব্যাক" : "জমা দেওয়া মতামত"} রাখা হয়।`],
        ["ঐচ্ছিক ব্যবহারের তথ্য", `আপনি অ্যানালিটিক্সে সম্মতি দিলে পৃষ্ঠা, ফিচার ইভেন্ট, ভাষা, প্রচারণার উৎস ও ছদ্মনামযুক্ত সেশন শনাক্তকারী আমাদের সার্ভারে সংগ্রহ করা হয়। কাঁচা সেশন আইডি সার্ভারে গোপন কী দিয়ে হ্যাশ করা হয়। প্রত্যাখ্যান করলে এই সংগ্রহ বন্ধ থাকে। ${researchBeta ? "গবেষণা বেটায়" : "এই সেবায়"} Google Analytics বা বিজ্ঞাপনের ট্র্যাকার ব্যবহার করা হয় না।`],
        ["কেন ব্যবহার করি", "সেবা চালানো, অ্যালার্ট পাঠানো, নিরাপত্তা ও অপব্যবহার প্রতিরোধ, সমস্যা নির্ণয়, ব্যবহারকারীর যাত্রা উন্নত করা এবং সম্মত প্রাতিষ্ঠানিক অনুরোধের উত্তর দিতে তথ্য ব্যবহার করি।"],
        ["শেয়ার ও বিক্রি", "ব্যক্তিগত তথ্য বিক্রি করি না। হোস্টিং, ইমেইল, অ্যানালিটিক্স বা আইনগত প্রয়োজনে সীমিত সেবাদাতা তথ্য প্রক্রিয়া করতে পারে। কোনো পোর্টফোলিও স্পষ্ট সম্মতি ছাড়া পাবলিক হয় না।"],
        ["সংরক্ষণ ও নিয়ন্ত্রণ", `কাঁচা পণ্য অ্যানালিটিক্স সর্বোচ্চ ১৮০ দিন এবং ${researchBeta ? "বেটা ফিডব্যাক" : "জমা দেওয়া মতামত"} সর্বোচ্চ ৩৬৫ দিন রাখা হয়। অ্যাকাউন্ট, যোগাযোগের তথ্য বা মুছে ফেলার অনুরোধের জন্য সহায়তা ইমেইলে লিখুন। কিছু নিরাপত্তা ও আইনগত রেকর্ড সীমিত সময় রাখা হতে পারে। অ্যানালিটিক্স সেটিংস আমি পৃষ্ঠা থেকে যেকোনো সময় বদলানো যায়।`],
        ["যোগাযোগ", `গোপনীয়তা সংক্রান্ত প্রশ্ন: ${config.support_email}`],
      ]
    : [
        ["Information we collect", `When you create an account we store your name, email or phone, and a secure password hash. We store watchlists, alerts, manually entered portfolios and community content when you use those features. Research-interview forms store submitted contact details, and ${researchBeta ? "beta feedback" : "submitted feedback"} stores the submitted report.`],
        ["Optional usage data", `If you consent to analytics, pages, feature events, locale, campaign attribution and a pseudonymous session identifier are collected on our service. Raw session identifiers are keyed-hashed before server storage. This collection stays off when you reject analytics. ${researchBeta ? "The research beta" : "The service"} uses no Google Analytics or advertising tracker.`],
        ["How we use it", "We use information to operate alerts and accounts, protect the service, diagnose failures, improve activation and respond to institutional enquiries that explicitly consented to contact."],
        ["Sharing and sale", "We do not sell personal information. Limited providers may process data for hosting, email, analytics or legal compliance. A portfolio is not public unless its owner explicitly enables public visibility."],
        ["Retention and control", `Raw product analytics are retained for at most 180 days and ${researchBeta ? "beta feedback" : "submitted feedback"} for at most 365 days. Contact support to request account access, correction or deletion. Some security and legal records may need to remain for a limited period. Analytics consent can be changed from the Me page.`],
        ["Contact", `Privacy questions: ${config.support_email}`],
      ];

  const termsSections = bn
    ? [
        [researchBeta ? "বেটা ও সেবার উদ্দেশ্য" : "সেবার উদ্দেশ্য", `${config.brand_name} একটি বিনামূল্যের, পরিবর্তনশীল ${researchBeta ? "গবেষণা বেটা" : "গবেষণা প্ল্যাটফর্ম"} যা বাজার গবেষণা ও শিক্ষার জন্য বর্ণনামূলক তথ্য দেয়। এটি বাণিজ্যিক গবেষণা সেবা, ব্রোকার, এক্সচেঞ্জ বা ব্যক্তিগত বিনিয়োগ উপদেষ্টা নয় এবং অর্ডার গ্রহণ করে না।`],
        ["কোনো বিনিয়োগ পরামর্শ নয়", "কোনো স্ক্রিন, স্কোর, অ্যালার্ট, স্বয়ংক্রিয় সারাংশ বা কমিউনিটি পোস্ট কেনা, বিক্রি বা ধরে রাখার সুপারিশ নয়। বিনিয়োগে মূলধন হারানোর ঝুঁকি আছে; প্রয়োজন হলে নিবন্ধিত পেশাদারের পরামর্শ নিন।"],
        ["তথ্যের সীমাবদ্ধতা", "তথ্য বিলম্বিত, অসম্পূর্ণ, সংশোধিত বা সাময়িকভাবে অনুপলব্ধ হতে পারে। উৎস ও as-of সময় যাচাই করা এবং নিজের সিদ্ধান্তের দায়িত্ব ব্যবহারকারীর।"],
        ["গ্রহণযোগ্য ব্যবহার", "স্বয়ংক্রিয় স্ক্র্যাপিং, নিরাপত্তা পরীক্ষা, ভুয়া পরিচয়, স্প্যাম, বাজার কারসাজি, বিভ্রান্তিকর দাবি, হয়রানি বা আইনবিরুদ্ধ ব্যবহার নিষিদ্ধ। অনুমতি ছাড়া ডেটা পুনঃবিতরণ করা যাবে না।"],
        ["ব্যবহারকারীর কনটেন্ট", "আপনি যে কনটেন্ট পোস্ট করেন তার দায়িত্ব আপনার। আমরা নীতিভঙ্গকারী কনটেন্ট পর্যালোচনা, সীমিত বা অপসারণ করতে এবং প্রয়োজনে অ্যাকাউন্ট স্থগিত করতে পারি।"],
        [researchBeta ? "বেটার সীমা" : "সেবার সীমা", `${researchBeta ? "বেটা লেবেল" : "সেবার কোনো লেবেল বা উপস্থাপনা"} কোনো তথ্যের নির্ভুলতা, নিয়ন্ত্রক অনুমোদন বা উৎসের ডেটা অধিকার নিশ্চিত করে না। সেবা পরিবর্তন, সীমিত বা বন্ধ হতে পারে। গুরুত্বপূর্ণ শর্ত পরিবর্তন হলে এই পৃষ্ঠার তারিখ হালনাগাদ করা হবে।`],
        ["যোগাযোগ", `শর্তাবলি বা সেবা সংক্রান্ত প্রশ্ন: ${config.support_email}`],
      ]
    : [
        [researchBeta ? "Beta and purpose" : "Purpose of the service", `${config.brand_name} is a free, evolving ${researchBeta ? "research beta" : "research platform"} providing descriptive information for market research and education. It is not a commercial research service, broker, exchange or personalized investment adviser and does not accept orders.`],
        ["No investment advice", "No screen, score, alert, automated summary or community post is a recommendation to buy, sell or hold a security. Investing can result in loss of capital. Use an appropriately registered professional when advice is required."],
        ["Data limitations", "Information may be delayed, incomplete, corrected or temporarily unavailable. Users are responsible for checking the source and as-of time and for their own decisions."],
        ["Acceptable use", "Automated extraction, unauthorized security testing, false identities, spam, market manipulation, misleading claims, harassment and unlawful activity are prohibited. Data may not be redistributed without permission."],
        ["User content", "You are responsible for content you submit. We may review, limit or remove policy-violating content and suspend accounts when required to protect the service or its users."],
        [researchBeta ? "Beta limitations" : "Service limitations", `${researchBeta ? "A beta label" : "No service label or presentation"} guarantees data accuracy, regulatory approval or rights in source data. The service may change, be limited or stop. Material revisions to these terms will update the effective date on this page.`],
        ["Contact", `Terms or service questions: ${config.support_email}`],
      ];

  const sections = privacy ? privacySections : termsSections;
  return (
    <article>
      <header className="border-b border-border pb-4">
        <h1 className="text-2xl font-extrabold">{title}</h1>
        <p className="mt-1 text-xs text-muted">{bn ? "কার্যকর: ১২ জুলাই ২০২৬" : "Effective: 12 July 2026"}</p>
      </header>
      <div className="divide-y divide-border">
        {sections.map(([heading, body]) => (
          <section key={heading} className="py-4">
            <h2 className="text-sm font-bold">{heading}</h2>
            <p className="mt-1 text-xs leading-relaxed text-muted">{body}</p>
          </section>
        ))}
      </div>
    </article>
  );
}

export function Privacy() {
  return <PolicyPage kind="privacy" />;
}

export function Terms() {
  return <PolicyPage kind="terms" />;
}
