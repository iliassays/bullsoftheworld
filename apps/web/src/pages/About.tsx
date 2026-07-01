import { Link } from "react-router-dom";
import { useLang } from "../lib/i18n";
import { DeskIcon } from "../lib/deskIcons";
import { VerifiedBadge } from "../components/ui";

const FB_URL = "https://www.facebook.com/1214682241723822";

// A few desk handles to showcase "meet the desks".
const SHOWCASE = [
  "BullsOfDhakaVolume",
  "BullsOfDhakaCircuit",
  "BullsOfDhakaBreakout",
  "BullsOfDhakaSmartMoney",
  "BullsOfDhakaDividend",
  "BullsOfDhakaAccumulation",
];

export function About() {
  const { lang } = useLang();
  const bn = lang === "bn";

  const principles = bn
    ? [
        { icon: "📊", t: "তথ্য, গুজব নয়", d: "আমরা বাজারের তথ্য দেখাই — টিপস বা গুজব নয়।" },
        { icon: "🚫", t: "কোনো কেনা-বেচার পরামর্শ নয়", d: "ডেটা কী বলছে তা বর্ণনা করি; সিদ্ধান্ত আপনার।" },
        { icon: "⏱️", t: "বিলম্বিত, তবে সৎ", d: "প্রতিটি সংখ্যা ‘বিলম্বিত / as-of’ স্ট্যাম্প করা — আমরা তথ্যকে টাটকা বলে চালাই না।" },
        { icon: "🐂", t: "অফিসিয়াল ডেস্ক", d: "ভেরিফায়েড স্বয়ংক্রিয় ডেস্ক সারা বাজার জুড়ে শুধু তথ্য পোস্ট করে।" },
      ]
    : [
        { icon: "📊", t: "Facts, not rumours", d: "We show what the market data says — never tips or hype." },
        { icon: "🚫", t: "No buy/sell advice", d: "We describe what the data shows; the decision is yours." },
        { icon: "⏱️", t: "Delayed, but honest", d: "Every number is stamped delayed / as-of. We never fake freshness." },
        { icon: "🐂", t: "Official desks", d: "Verified automated desks post facts across the whole market." },
      ];

  return (
    <div className="flex flex-col gap-4">
      {/* Hero */}
      <div className="bg-card rounded-2xl overflow-hidden">
        <div className="h-1.5 bg-accent" />
        <div className="p-6 text-center">
          <img
            src="/logo-mark-v2.png"
            alt="Bulls of Dhaka"
            className="w-16 h-16 mx-auto"
          />
          <h1 className="text-2xl font-extrabold mt-3">Bulls of Dhaka</h1>
          <div className="text-accent font-semibold text-sm mt-0.5">
            {bn ? "তথ্য চলুন, গুজবে নয়" : "Facts, not rumours"}
          </div>
          <p className="text-sm text-muted leading-relaxed mt-3 max-w-md mx-auto">
            {bn
              ? "ঢাকা স্টক এক্সচেঞ্জের প্রাতিষ্ঠানিক মানের ডেটা — সাধারণ বিনিয়োগকারীর জন্য সহজ, সৎ ও বিনামূল্যে।"
              : "Institution-grade Dhaka Stock Exchange data — made simple, honest, and free to explore for every retail investor."}
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
      <div className="bg-surface border border-border rounded-2xl p-4">
        <div className="flex items-center gap-1.5 font-bold text-sm">
          {bn ? "অফিসিয়াল ডেস্কের সাথে পরিচিত হোন" : "Meet the official desks"}
          <VerifiedBadge size={15} />
        </div>
        <p className="text-xs text-muted mt-1 leading-relaxed">
          {bn
            ? "প্রতিটি ডেস্ক একটি বিষয়ে নজর রাখে এবং উল্লেখযোগ্য কিছু ঘটলেই শুধু তথ্য পোস্ট করে। ফলো করুন — তাদের পোস্ট আপনার ফিডে আসবে।"
            : "Each desk watches one beat and posts a fact only when something notable happens. Follow the ones you care about — their posts flow into your feed."}
        </p>
        <div className="flex flex-wrap gap-2.5 mt-3 text-accent">
          {SHOWCASE.map((h) => (
            <div
              key={h}
              className="w-10 h-10 rounded-full grid place-items-center bg-card border border-accent/40"
            >
              <DeskIcon handle={h} size={20} />
            </div>
          ))}
        </div>
      </div>

      {/* CTA */}
      <div className="bg-card rounded-2xl p-5 text-center">
        <div className="font-bold">
          {bn ? "সাথে থাকুন" : "Stay in the loop"}
        </div>
        <p className="text-xs text-muted mt-1">
          {bn
            ? "প্রতিদিনের মার্কেট আপডেট ফেসবুকে পান, আর অ্যাপে সব ডেস্কের ফিড দেখুন।"
            : "Get the daily market wrap on Facebook, and the full desk feed in the app."}
        </p>
        <div className="flex gap-2 justify-center mt-3">
          <a
            href={FB_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-full px-4 py-2 text-sm font-bold bg-accent text-bg hover:opacity-90"
          >
            {bn ? "ফেসবুকে ফলো করুন" : "Follow on Facebook"}
          </a>
          <Link
            to="/bulls"
            className="rounded-full px-4 py-2 text-sm font-semibold border border-border hover:border-accent hover:text-accent"
          >
            🐂 {bn ? "বুলস ফিড" : "Bulls feed"}
          </Link>
        </div>
      </div>

      <p className="text-[10.5px] text-muted text-center leading-relaxed px-4">
        {bn
          ? "শুধুই তথ্য · কোনো বিনিয়োগ পরামর্শ নয় · DSE EOD ডেটা, সংশোধনযোগ্য"
          : "Data only · Not investment advice · DSE EOD data, subject to correction"}
      </p>
    </div>
  );
}
