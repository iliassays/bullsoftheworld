import { useEffect, useState } from "react";
import { api, type MoodIndex } from "../lib/api";
import { useLang } from "../lib/i18n";

// Dhaka Mood Index — a descriptive market-wide fear/greed gauge. The score, band label, caption and
// component/context strings all arrive localized from the API; this just draws them. No advice.

// Five colour zones (fear → greed), matching the 0..100 dial. Endpoints precomputed from the arc
// geometry in cards.py's gauge so the segments line up; see build_mood for the band thresholds.
const ZONES = [
  { d: "M65,175 A135 135 0 0 1 104.5,79.5", c: "#e0414d" },
  { d: "M104.5,79.5 A135 135 0 0 1 178.9,41.7", c: "#e8804a" },
  { d: "M178.9,41.7 A135 135 0 0 1 221.1,41.7", c: "#d9b53a" },
  { d: "M221.1,41.7 A135 135 0 0 1 295.5,79.5", c: "#2bb673" },
  { d: "M295.5,79.5 A135 135 0 0 1 335,175", c: "#16c784" },
];

function bandText(band: MoodIndex["band"]): string {
  if (band === "fear" || band === "extreme_fear") return "text-down";
  if (band === "greed" || band === "extreme_greed") return "text-up";
  return "text-accent";
}

export function DhakaMood() {
  const { lang } = useLang();
  const [mood, setMood] = useState<MoodIndex | null>(null);

  // Refetch when language flips — the server localizes the label/caption/components.
  useEffect(() => {
    let live = true;
    api
      .marketMood()
      .then((m) => live && setMood(m))
      .catch(() => live && setMood(null));
    return () => {
      live = false;
    };
  }, [lang]);

  if (!mood) return null;

  const bn = lang === "bn";
  const score = mood.score;
  // Needle angle: 0 → 180° (left), 100 → 0° (right). Park at centre when the score is unknown.
  const angle = ((180 - 1.8 * (score ?? 50)) * Math.PI) / 180;
  const nx = 200 + 112 * Math.cos(angle);
  const ny = 175 - 112 * Math.sin(angle);

  return (
    <div className="rounded-2xl border border-border bg-card p-4">
      <div className="flex items-baseline justify-between">
        <div className="text-sm font-extrabold">
          {bn ? "ঢাকা মুড ইনডেক্স" : "Dhaka Mood Index"}
          <span className="ml-2 text-[10px] font-semibold text-muted">
            {bn ? "Dhaka Mood Index" : "ঢাকা মুড ইনডেক্স"}
          </span>
        </div>
        {mood.as_of_date && (
          <div className="text-[10px] text-muted">
            {bn ? "তথ্য" : "as of"} {mood.as_of_date}
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
              stroke="#f5b82e"
              strokeWidth="4.5"
              strokeLinecap="round"
            />
            <circle cx="200" cy="175" r="9" fill="#f5b82e" />
            <circle cx="200" cy="175" r="4" fill="#0b0e11" />
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

      <p className="mt-3 text-[13px] leading-relaxed">{mood.caption}</p>
      <p className="mt-2 border-t border-border pt-2 text-[10.5px] leading-snug text-muted">
        {mood.disclaimer}
      </p>
    </div>
  );
}
