import { useEffect, useState } from "react";
import { api, type Pulse } from "../lib/api";
import { useLang } from "../lib/i18n";

// Pulse — three descriptive dials from community activity. Counts only, no advice.
export function PulseGauges({ code }: { code: string }) {
  const { t } = useLang();
  const [pulse, setPulse] = useState<Pulse | null>(null);

  useEffect(() => {
    setPulse(null);
    api
      .pulse(code)
      .then(setPulse)
      .catch(() => setPulse(null));
  }, [code]);

  if (!pulse) return null;

  const sentColor =
    pulse.sentiment.score >= 55
      ? "bg-up"
      : pulse.sentiment.score <= 45
        ? "bg-down"
        : "bg-muted";

  // Backend returns English value words (Mixed / Low / High …); map to the chosen language.
  const word = (label: string) => {
    const tr = t(`pv.${label.toLowerCase()}`);
    return tr.startsWith("pv.") ? label : tr;
  };
  const row = (
    title: string,
    g: { score: number; label: string },
    barCls: string,
  ) => (
    <div className="py-2">
      <div className="flex items-baseline justify-between text-xs">
        <span className="text-muted">{title}</span>
        <span className="font-semibold capitalize">
          {word(g.label)} <span className="text-muted tnum">· {g.score}</span>
        </span>
      </div>
      <div className="mt-1 h-1.5 rounded-full bg-border overflow-hidden">
        <div className={`h-full ${barCls}`} style={{ width: `${g.score}%` }} />
      </div>
    </div>
  );

  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <div className="text-accent font-semibold text-sm">📊 {t("pulse.title")}</div>
      <p className="text-[10px] text-muted mb-1">{t("pulse.subtitle")}</p>
      {row(t("pulse.sentiment"), pulse.sentiment, sentColor)}
      {row(t("pulse.volume"), pulse.message_volume, "bg-accent")}
      {row(t("pulse.participation"), pulse.participation, "bg-accent")}
    </div>
  );
}
