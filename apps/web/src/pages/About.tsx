import { useEffect, useState } from "react";
import { Link } from "../lib/nav";
import { api, type NoteBeat } from "../lib/api";
import { useLang } from "../lib/i18n";
import { DeskIcon } from "../lib/deskIcons";
import { useSeo } from "../components/Seo";
import { VerifiedBadge } from "../components/ui";
import { useTenantConfig } from "../lib/tenant";

export function About() {
  const { lang } = useLang();
  const { config } = useTenantConfig();
  const bn = lang === "bn";
  const exchange = bn ? config.exchange_name_bn || config.exchange_name : config.exchange_name;
  useSeo({
    title: {
      bn: `${config.brand_name} সম্পর্কে — ${exchange}-এর জন্য তথ্যভিত্তিক প্ল্যাটফর্ম`,
      en: `About ${config.brand_name} — a facts-first platform for ${exchange}`,
    },
    description: {
      bn: `${config.brand_name} কী, কেন '${config.tagline_bn}', আর কীভাবে ${exchange}-এর তথ্য সহজভাবে তুলে ধরে।`,
      en: `What ${config.brand_name} is, why '${config.tagline_en}', and how it makes ${exchange} data easier to understand.`,
    },
  });
  const [desks, setDesks] = useState<NoteBeat[]>([]);
  useEffect(() => {
    if (!config.features.automated_desks) {
      setDesks([]);
      return;
    }
    api
      .noteBeats()
      .then(setDesks)
      .catch(() => setDesks([]));
  }, [config.features.automated_desks]);

  const principles = bn
    ? [
        { icon: "📊", t: "তথ্য, গুজব নয়", d: "আমরা বাজারের তথ্য দেখাই — টিপস বা গুজব নয়।" },
        { icon: "🚫", t: "কোনো কেনা-বেচার পরামর্শ নয়", d: "ডেটা কী বলছে তা বর্ণনা করি; সিদ্ধান্ত আপনার।" },
        { icon: "⏱️", t: "বিলম্বিত, তবে সৎ", d: "প্রতিটি সংখ্যা ‘বিলম্বিত / as-of’ স্ট্যাম্প করা — আমরা তথ্যকে টাটকা বলে চালাই না।" },
        ...(config.features.automated_desks
          ? [{ icon: "🐂", t: "অফিসিয়াল ডেস্ক", d: "ভেরিফায়েড স্বয়ংক্রিয় ডেস্ক সারা বাজার জুড়ে শুধু তথ্য পোস্ট করে।" }]
          : []),
      ]
    : [
        { icon: "📊", t: "Facts, not rumours", d: "We show what the market data says — never tips or hype." },
        { icon: "🚫", t: "No buy/sell advice", d: "We describe what the data shows; the decision is yours." },
        { icon: "⏱️", t: "Delayed, but honest", d: "Every number is stamped delayed / as-of. We never fake freshness." },
        ...(config.features.automated_desks
          ? [{ icon: "🐂", t: "Official desks", d: "Verified automated desks post facts across the whole market." }]
          : []),
      ];

  return (
    <div className="flex flex-col gap-4">
      {/* Hero */}
      <div className="bg-card rounded-2xl overflow-hidden">
        <div className="h-1.5 bg-accent" />
        <div className="p-6 text-center">
          <img
            src={config.logo_url}
            alt={config.brand_name}
            className="w-16 h-16 mx-auto"
          />
          <h1 className="text-2xl font-extrabold mt-3">{config.brand_name}</h1>
          <div className="text-accent font-semibold text-sm mt-0.5">
            {bn ? config.tagline_bn : config.tagline_en}
          </div>
          <p className="text-sm text-muted leading-relaxed mt-3 max-w-md mx-auto">
            {bn
              ? `${exchange}-এর তথ্য — সাধারণ বিনিয়োগকারীর জন্য সহজ, সৎ ও বিনামূল্যে।`
              : `${exchange} data — made simple, honest, and free to explore for retail investors.`}
          </p>
        </div>
      </div>

      {/* Principles */}
      <div className="grid grid-cols-2 gap-2.5">
        {principles.map((p) => (
          <div key={p.t} className="bg-surface border border-border rounded-2xl p-4">
            <div className="text-2xl">{p.icon}</div>
            <div className="font-bold text-sm mt-2">{p.t}</div>
            <p className="text-xs text-muted leading-relaxed mt-1">{p.d}</p>
          </div>
        ))}
      </div>

      {/* Meet the desks */}
      {config.features.automated_desks && <div className="bg-surface border border-border rounded-2xl p-4">
        <div className="flex items-center gap-1.5 font-bold text-sm">
          {bn ? "অফিসিয়াল ডেস্কের সাথে পরিচিত হোন" : "Meet the official desks"}
          <VerifiedBadge size={15} />
        </div>
        <p className="text-xs text-muted mt-1 leading-relaxed">
          {bn
            ? "প্রতিটি ডেস্ক একটি বিষয়ে নজর রাখে এবং উল্লেখযোগ্য কিছু ঘটলেই শুধু তথ্য পোস্ট করে। ফলো করুন — তাদের পোস্ট আপনার ফিডে আসবে।"
            : "Each desk watches one beat and posts a fact only when something notable happens. Follow the ones you care about — their posts flow into your feed."}
        </p>
        <div className="grid grid-cols-2 gap-2 mt-3">
          {desks.map((d) => (
            <Link
              key={d.handle}
              to={`/desk/${d.handle}`}
              className="flex items-center gap-2.5 rounded-xl border border-border bg-card px-3 py-2 hover:border-accent transition"
            >
              <span className="w-8 h-8 shrink-0 rounded-full grid place-items-center bg-surface border border-accent/40 text-accent">
                <DeskIcon handle={d.handle} size={17} />
              </span>
              <span className="text-[13px] font-semibold truncate">{d.name}</span>
            </Link>
          ))}
        </div>
      </div>}

      {/* CTA */}
      <div className="bg-card rounded-2xl p-5 text-center">
        <div className="font-bold">
          {bn ? "সাথে থাকুন" : "Stay in the loop"}
        </div>
        <p className="text-xs text-muted mt-1">
          {bn
            ? config.social_url
              ? "প্রতিদিনের মার্কেট আপডেট ফেসবুকে পান, আর অ্যাপে সব ডেস্কের ফিড দেখুন।"
              : "আপনার পছন্দের শেয়ার ও বাজারের আলোচনা অ্যাপে অনুসরণ করুন।"
            : config.social_url
              ? "Get the daily market wrap on Facebook, and the full desk feed in the app."
              : "Follow the stocks and market discussions you care about in the app."}
        </p>
        <div className="flex gap-2 justify-center mt-3">
          {config.social_url && (
            <a
              href={config.social_url}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-full px-4 py-2 text-sm font-bold bg-accent text-bg hover:opacity-90"
            >
              {bn ? "ফেসবুকে ফলো করুন" : "Follow on Facebook"}
            </a>
          )}
          <Link
            to={config.features.automated_desks ? "/bulls" : "/watchlist"}
            className="rounded-full px-4 py-2 text-sm font-semibold border border-border hover:border-accent hover:text-accent"
          >
            {config.features.automated_desks
              ? `🐂 ${bn ? "বুলস ফিড" : "Bulls feed"}`
              : `☆ ${bn ? "ওয়াচলিস্ট" : "Watchlist"}`}
          </Link>
        </div>
      </div>

      <p className="text-[10.5px] text-muted text-center leading-relaxed px-4">
        {bn
          ? `শুধুই তথ্য · কোনো বিনিয়োগ পরামর্শ নয় · ${config.exchange_code} ডেটা, সংশোধনযোগ্য`
          : `Data only · Not investment advice · ${config.exchange_code} data, subject to correction`}
      </p>
    </div>
  );
}
