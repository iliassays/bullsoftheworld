import { useEffect } from "react";
import { useSeo } from "../components/Seo";
import { trackProductEvent } from "../lib/analytics";
import { useLang } from "../lib/i18n";
import { useTenantConfig } from "../lib/tenant";

export function Trust() {
  const { lang } = useLang();
  const { config } = useTenantConfig();
  const bn = lang === "bn";
  const exchange = bn ? config.exchange_name_bn || config.exchange_name : config.exchange_name;
  useSeo({
    title: { bn: `তথ্য ও পদ্ধতি — ${config.brand_name}`, en: `Data and methodology — ${config.brand_name}` },
    description: { bn: `${config.brand_name} কীভাবে তথ্যের উৎস, সময় ও সীমাবদ্ধতা দেখায়।`, en: `How ${config.brand_name} handles sources, freshness, calculations and limitations.` },
  });
  useEffect(() => {
    trackProductEvent("view_trust", { market: config.market, source: "trust_page" });
  }, [config.market]);

  const sections = bn
    ? [
        ["প্রমাণ আগে", `প্রতিটি ব্যাখ্যার ভিত্তি হলো ${exchange}-এর বাজার তথ্য, প্রকাশিত কোম্পানি তথ্য বা স্পষ্টভাবে চিহ্নিত প্ল্যাটফর্ম সিগন্যাল। অফিসিয়াল কারণ না থাকলে আমরা তা বলি।`],
        ["সময় ও বিলম্ব", "লাইভ, বিলম্বিত ও দিনের-শেষের তথ্য এক নয়। প্রাসঙ্গিক স্ক্রিনে as-of সময় দেখানো হয়; পুরোনো তথ্যকে নতুন হিসেবে দেখানো হয় না।"],
        ["গণনা ও ব্যাখ্যা", "মূল্য, ভলিউম, তারল্য, টেকনিক্যাল, মূল্যায়ন ও মালিকানার মাপকাঠি নির্ধারিত নিয়মে হিসাব করা হয়। ব্যাখ্যা তথ্যকে সহজ করে, ভবিষ্যৎ নিশ্চিত করে না। ব্যবহারকারীর আগ্রহভিত্তিক মাপকাঠি শুধু অ্যানালিটিক্সে সম্মত ব্যবহারকারীদের নমুনা থেকে আসতে পারে এবং পুরো বাজারের প্রতিনিধিত্ব করে না।"],
        ["স্বয়ংক্রিয় বিশ্লেষণ", "কিছু সারাংশ স্বয়ংক্রিয়ভাবে তৈরি হয়। উত্তর উৎসভিত্তিক রাখার চেষ্টা করা হলেও অসম্পূর্ণতা বা ভুল থাকতে পারে। উদ্ধৃত উৎস ও তারিখ যাচাই করুন।"],
        ["কোনো পরামর্শ নয়", "আমরা ব্রোকার নই, অর্ডার নিই না এবং ব্যক্তিগত কেনা-বেচার পরামর্শ দিই না। আপনার লক্ষ্য, ঝুঁকি ও আর্থিক অবস্থা আমরা জানি না।"],
        ["সংশোধন", `কোনো ভুল দেখলে টিকার, পৃষ্ঠা ও উৎসসহ ${config.support_email}-এ পাঠান। যাচাইযোগ্য সংশোধনকে অগ্রাধিকার দেওয়া হয়।`],
      ]
    : [
        ["Evidence first", `Interpretation starts with ${exchange} market data, published company information or clearly labelled platform signals. When no official catalyst is found, we say so.`],
        ["Freshness and delay", "Live, delayed and end-of-day data are different products. Relevant screens show an as-of time; stale evidence is never presented as current."],
        ["Calculation and interpretation", "Price, volume, liquidity, technical, valuation and ownership measures use deterministic rules. Interpretation makes facts easier to inspect; it does not make the future certain. Usage-based attention measures may use only the consented-user sample and are not representative of the whole market."],
        ["Automated analysis", "Some summaries are generated automatically. They are designed to remain source-grounded but can still be incomplete or wrong. Review the cited source and date."],
        ["No advice", "We are not a broker, do not accept orders and do not provide personalized buy or sell advice. We do not know your objectives, risk tolerance or financial position."],
        ["Corrections", `Report an issue with the ticker, page and source to ${config.support_email}. Verifiable corrections are prioritized.`],
      ];

  return (
    <article>
      <header className="border-b border-border pb-4">
        <div className="text-[10px] font-semibold uppercase tracking-wide text-accent">{bn ? "বিশ্বাস ও স্বচ্ছতা" : "Trust and transparency"}</div>
        <h1 className="mt-1 text-2xl font-extrabold">{bn ? "তথ্য কীভাবে তৈরি ও দেখানো হয়" : "How the evidence is built and presented"}</h1>
        <p className="mt-2 text-sm leading-relaxed text-muted">{bn ? "ভালো সিদ্ধান্তের শুরু পরিষ্কার উৎস, সঠিক সময় ও সীমাবদ্ধতা জানা থেকে।" : "Sound research starts with clear sources, timestamps and limitations."}</p>
      </header>
      <div className="divide-y divide-border">
        {sections.map(([title, body]) => (
          <section key={title} className="py-4">
            <h2 className="text-sm font-bold">{title}</h2>
            <p className="mt-1 text-xs leading-relaxed text-muted">{body}</p>
          </section>
        ))}
      </div>
    </article>
  );
}
