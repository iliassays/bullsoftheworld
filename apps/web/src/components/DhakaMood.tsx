import { useEffect, useState } from "react";
import { api, type MoodIndex } from "../lib/api";
import { useLang } from "../lib/i18n";

// Dhaka Mood Index — a descriptive market-wide fear/greed gauge. The score, band label, caption and
// component/context strings all arrive localized from the API; this just draws them. No advice.

// Five colour zones (fear → greed), matching the 0..100 dial. Endpoints precomputed from the arc
// geometry in cards.py's gauge so the segments line up; see build_mood for the band thresholds.
// Fear → greed ramp. The endpoints are the app's theme red/green (#f0564a / #2fbf71); the middle
// three are intermediate gradient steps.
const ZONES = [
  { d: "M65,175 A135 135 0 0 1 104.5,79.5", c: "#f0564a" },
  { d: "M104.5,79.5 A135 135 0 0 1 178.9,41.7", c: "#e8804a" },
  { d: "M178.9,41.7 A135 135 0 0 1 221.1,41.7", c: "#d9b53a" },
  { d: "M221.1,41.7 A135 135 0 0 1 295.5,79.5", c: "#2bb673" },
  { d: "M295.5,79.5 A135 135 0 0 1 335,175", c: "#2fbf71" },
];

function bandText(band: MoodIndex["band"]): string {
  if (band === "fear" || band === "extreme_fear") return "text-down";
  if (band === "greed" || band === "extreme_greed") return "text-up";
  return "text-accent";
}

export function DhakaMood() {
  const { lang } = useLang();
  const [mood, setMood] = useState<MoodIndex | null>(null);

  // The quote worker writes every 15 minutes. Match that cadence and refresh immediately when a
  // user returns to the tab so an old close never remains on screen through an active session.
  useEffect(() => {
    let live = true;
    const load = () => {
      api
        .marketMood()
        .then((m) => live && setMood(m))
        .catch(() => live && setMood(null));
    };
    const refreshWhenVisible = () => {
      if (document.visibilityState === "visible") load();
    };

    load();
    const timer = window.setInterval(load, 15 * 60 * 1000);
    document.addEventListener("visibilitychange", refreshWhenVisible);
    return () => {
      live = false;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
    };
  }, [lang]);

  if (!mood) return null;

  const bn = lang === "bn";
  const score = mood.score;
  // Needle angle: 0 → 180° (left), 100 → 0° (right). Park at centre when the score is unknown.
  const angle = ((180 - 1.8 * (score ?? 50)) * Math.PI) / 180;
  const nx = 200 + 112 * Math.cos(angle);
  const ny = 175 - 112 * Math.sin(angle);
  const quoteTime = mood.as_of
    ? new Intl.DateTimeFormat(bn ? "bn-BD" : "en-GB", {
        timeZone: "Asia/Dhaka",
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).format(new Date(mood.as_of))
    : mood.as_of_date;
  const freshness =
    mood.data_status === "stale"
      ? bn
        ? "ডেটা আপডেট দেরি হচ্ছে"
        : "Data refresh is late"
      : mood.data_status === "intraday_delayed"
      ? bn
        ? "ইন্ট্রাডে · ১৫ মিনিট বিলম্বিত"
        : "Intraday · 15-min delayed"
      : mood.data_status === "provisional_close"
        ? bn
          ? "ক্লোজ-পরবর্তী প্রাথমিক স্ন্যাপশট"
          : "Provisional post-close snapshot"
        : bn
          ? "সর্বশেষ ক্লোজ"
          : "Latest close";
  const displayAsOf = mood.data_status === "official_close" ? mood.as_of_date : quoteTime;

  return (
    <div className="rounded-2xl border border-border bg-card p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="text-sm font-extrabold">
          {bn ? "ঢাকা মুড ইনডেক্স" : "Dhaka Mood Index"}
          <span className="ml-2 text-[10px] font-semibold text-muted">
            {bn ? "Dhaka Mood Index" : "ঢাকা মুড ইনডেক্স"}
          </span>
        </div>
        {mood.as_of_date && (
          <div className="shrink-0 text-right text-[10px] leading-relaxed" aria-live="polite">
            <div
              className={
                mood.data_status === "stale"
                  ? "font-semibold text-down"
                  : mood.data_status === "official_close"
                    ? "text-muted"
                    : "font-semibold text-accent"
              }
            >
              {freshness}
            </div>
            <div className="text-muted">
              {bn ? "আপডেট" : "Updated"} {displayAsOf}
              {mood.data_status !== "official_close" && " BDT"}
            </div>
          </div>
        )}
      </div>

      <svg viewBox="0 0 400 236" className="w-full" role="img" aria-label={mood.label}>
        {ZONES.map((z) => (
          <path key={z.d} d={z.d} fill="none" stroke={z.c} strokeWidth="22" />
        ))}
        {score != null && (
          <>
            <line
              x1="200"
              y1="175"
              x2={nx}
              y2={ny}
              stroke="#e3b341"
              strokeWidth="4.5"
              strokeLinecap="round"
            />
            <circle cx="200" cy="175" r="9" fill="#e3b341" />
            <circle cx="200" cy="175" r="4" fill="#0d1524" />
            <text
              x="200"
              y="150"
              textAnchor="middle"
              fill="#e8edf2"
              fontSize="44"
              fontWeight="800"
            >
              {score}
            </text>
          </>
        )}
        <text
          x="200"
          y="206"
          textAnchor="middle"
          className={bandText(mood.band)}
          fill="currentColor"
          fontSize="16"
          fontWeight="800"
        >
          {mood.label}
        </text>
        <text x="60" y="200" textAnchor="middle" fill="#8b97a6" fontSize="11">
          {bn ? "ভয়" : "Fear"}
        </text>
        <text x="340" y="200" textAnchor="middle" fill="#8b97a6" fontSize="11">
          {bn ? "লোভ" : "Greed"}
        </text>
      </svg>

      <div className="mt-2 flex flex-wrap gap-1.5">
        {mood.components.map((c) => (
          <span
            key={c.key}
            className="rounded-full border border-border bg-surface px-2.5 py-1 text-[11px]"
          >
            {c.label} <b className="text-text">{c.detail}</b>
          </span>
        ))}
        {mood.context.map((c) => (
          <span
            key={c}
            className="rounded-full border border-border bg-surface px-2.5 py-1 text-[11px] text-muted"
          >
            {c}
          </span>
        ))}
      </div>

      {mood.data_status === "stale" ? (
        <p className="mt-2 text-[10px] leading-snug text-down">
          {bn
            ? "সর্বশেষ কোট নির্ধারিত সময়ে আসেনি। এই স্কোরকে চলতি সেশনের অবস্থা হিসেবে ধরবেন না।"
            : "The latest quote batch missed its expected time. Do not treat this score as the current session state."}
        </p>
      ) : mood.data_status !== "official_close" ? (
        <p className="mt-2 text-[10px] leading-snug text-muted">
          {bn
            ? `ব্রেডথ, শক্তি ও ৫২-সপ্তাহের অবস্থান সর্বশেষ বিলম্বিত দামে; অস্থিরতা ${mood.close_as_of_date ?? "সর্বশেষ"} ক্লোজ পর্যন্ত।`
            : `Breadth, strength and 52-week position use the latest delayed prices; volatility is through the ${mood.close_as_of_date ?? "latest"} close.`}
        </p>
      ) : null}

      <p className="mt-3 text-[13px] leading-relaxed">{mood.caption}</p>
      <p className="mt-2 border-t border-border pt-2 text-[10.5px] leading-snug text-muted">
        {mood.disclaimer}
      </p>
    </div>
  );
}
