import { useEffect, useState } from "react";
import { api, type PlainRead } from "../lib/api";
import { useLang } from "../lib/i18n";

// Small emoji per point category — a quick visual anchor, not decoration overload.
const TAG_ICON: Record<string, string> = {
  size: "🏛️",
  trend: "📈",
  steadiness: "🌊",
  quality: "⭐",
  value: "🏷️",
  income: "💵",
  flow: "💧",
  smartmoney: "🏦",
  shortterm: "⏱️",
};

// The flagship "what does all this actually mean" card — a synthesised, plain-language read of the
// stock's whole factor profile, plus how traders generally read such a profile. Descriptive only.
export function PlainReadCard({ code }: { code: string }) {
  const { t } = useLang();
  const [read, setRead] = useState<PlainRead | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setRead(null);
    setFailed(false);
    api
      .plainRead(code)
      .then(setRead)
      .catch(() => setFailed(true));
  }, [code]);

  if (failed) return null;
  if (!read)
    return <div className="bg-surface border border-border rounded-2xl p-4 animate-pulse h-40" />;

  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <div className="text-accent font-semibold text-sm">🧭 {t("plainRead.title")}</div>
      <p className="text-[15px] font-semibold mt-1 leading-snug">{read.headline}</p>

      <ul className="mt-3 flex flex-col gap-1.5">
        {read.points.map((p, i) => (
          <li key={i} className="flex gap-2 text-[13px] leading-snug">
            <span className="shrink-0">{TAG_ICON[p.tag] ?? "•"}</span>
            <span>{p.text}</span>
          </li>
        ))}
      </ul>

      <div className="mt-3 rounded-xl bg-card border border-border p-3">
        <div className="text-[11px] uppercase tracking-wide text-muted mb-1">{t("plainRead.howTraders")}</div>
        <p className="text-[13px] leading-snug">{read.how_to_read}</p>
      </div>

      <p className="text-[10px] text-muted mt-2">{read.disclaimer}</p>
    </div>
  );
}
