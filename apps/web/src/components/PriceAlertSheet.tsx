import { useEffect, useState } from "react";
import { api, type PriceAlert as PriceAlertT } from "../lib/api";
import { useLang } from "../lib/i18n";
import { taka } from "./ui";

// Per-stock price alerts: a small sheet. Create "above/below ৳X" lines; the intraday poll
// triggers them into the Alerts inbox. Descriptive by design — a level you chose.
// Shared by Symbol (the header bell) and Portfolio (closing the "I bought it → watch it" loop).
export function PriceAlertSheet({
  code,
  onClose,
  onChange,
}: {
  code: string;
  onClose: () => void;
  // Portfolio shows a "has an alert" pill outside this sheet — without this, it goes stale
  // until the next full page reload after adding/removing an alert here.
  onChange?: () => void;
}) {
  const { t } = useLang();
  const [existing, setExisting] = useState<PriceAlertT[]>([]);
  const [level, setLevel] = useState("");
  const [direction, setDirection] = useState<"above" | "below">("above");
  const load = () =>
    api
      .priceAlerts(code)
      .then(setExisting)
      .catch(() => setExisting([]));
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code]);
  const add = async () => {
    const v = Number(level);
    if (!Number.isFinite(v) || v <= 0) return;
    await api.priceAlertCreate({ code, level: v, direction }).catch(() => {});
    setLevel("");
    load();
    onChange?.();
  };
  return (
    <div className="bg-surface border border-accent/40 rounded-2xl p-4 flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <div className="font-semibold text-sm">🔔 {t("pa.title")} ${code}</div>
        <button onClick={onClose} className="text-muted text-sm px-1" aria-label={t("pf.cancel")}>
          ✕
        </button>
      </div>
      {existing.map((a) => (
        <div key={a.id} className="flex items-center gap-2 text-sm tnum">
          <span>{a.direction === "above" ? "▲" : "▼"}</span>
          <span>{taka(a.level)}</span>
          {a.triggered_at && <span className="text-[10px] text-muted">{t("pa.triggered")}</span>}
          <button
            onClick={() => api.priceAlertDelete(a.id).then(load).then(() => onChange?.())}
            className="ml-auto text-muted text-xs hover:text-down"
          >
            {t("pa.remove")}
          </button>
        </div>
      ))}
      {existing.length === 0 && <div className="text-xs text-muted">{t("pa.none")}</div>}
      <div className="flex gap-2">
        <div className="flex rounded-xl border border-border overflow-hidden text-xs font-semibold">
          {(["above", "below"] as const).map((d) => (
            <button
              key={d}
              onClick={() => setDirection(d)}
              className={`px-3 py-2 ${direction === d ? "bg-accent text-bg" : "text-muted"}`}
            >
              {d === "above" ? `▲ ${t("pa.above")}` : `▼ ${t("pa.below")}`}
            </button>
          ))}
        </div>
        <input
          value={level}
          onChange={(e) => setLevel(e.target.value)}
          placeholder="৳"
          inputMode="decimal"
          className="bg-bg border border-border rounded-xl px-3 py-2 text-sm flex-1 tnum min-w-0"
        />
        <button
          onClick={add}
          className="rounded-xl px-4 text-sm font-bold bg-accent text-bg hover:opacity-90"
        >
          {t("pa.add")}
        </button>
      </div>
    </div>
  );
}
