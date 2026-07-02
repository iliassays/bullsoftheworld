import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type EarningsEvent } from "../lib/api";
import { useLang } from "../lib/i18n";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const WEEKDAYS = {
  en: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
  bn: ["রবি", "সোম", "মঙ্গল", "বুধ", "বৃহ", "শুক্র", "শনি"],
};

// "2026-07-07" → { day: "7 Jul", weekday: "Tue" }. Parsed as UTC so the weekday never drifts.
function fmt(iso: string, bn: boolean) {
  const [y, m, d] = iso.split("-").map(Number);
  const wd = new Date(Date.UTC(y, m - 1, d)).getUTCDay();
  return { day: `${d} ${MONTHS[m - 1] ?? "?"}`, weekday: WEEKDAYS[bn ? "bn" : "en"][wd] ?? "" };
}

// The DSE portal carries no company logos, so we use a deterministic monogram (ticker initials in a
// brand-tinted circle) — consistent, offline-safe, and carries no up/down meaning.
function Monogram({ code }: { code: string }) {
  return (
    <span className="flex-none w-8 h-8 rounded-full bg-accent/10 text-accent grid place-items-center text-[11px] font-bold">
      {code.slice(0, 2)}
    </span>
  );
}

// This week's earnings — DSE board meetings called to consider results, from decoded announcements.
// Descriptive heads-up only; hidden entirely when nothing is scheduled.
export function EarningsWeek() {
  const { t, lang } = useLang();
  const bn = lang === "bn";
  const [events, setEvents] = useState<EarningsEvent[] | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .earningsCalendar(7)
      .then((e) => alive && setEvents(e))
      .catch(() => alive && setEvents([]));
    return () => {
      alive = false;
    };
  }, []);

  if (!events || events.length === 0) return null;

  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <div className="font-semibold text-sm">📅 {t("home.earningsWeek")}</div>
      <p className="text-[12px] text-muted mt-0.5 leading-snug">{t("home.earningsWeekSub")}</p>
      <div className="mt-3 flex flex-col divide-y divide-border">
        {events.map((e) => {
          const { day, weekday } = fmt(e.meeting_date, bn);
          const period = e.period ? t(`news.period.${e.period}`) : "";
          return (
            <Link
              key={e.code}
              to={`/s/${e.code}`}
              className="flex items-center gap-3 py-2.5 first:pt-0 last:pb-0"
            >
              <Monogram code={e.code} />
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold">${e.code}</div>
                <div className="text-[11px] text-muted truncate">
                  {(bn && e.name_bn) || e.name_en}
                </div>
              </div>
              <div className="text-right flex-none">
                <div className="text-sm font-semibold text-accent tnum">{day}</div>
                <div className="text-[11px] text-muted">
                  {weekday}
                  {period ? ` · ${period}` : ""}
                </div>
              </div>
            </Link>
          );
        })}
      </div>
      <p className="text-[10px] text-muted mt-2">{t("home.earningsWeekNote")}</p>
    </div>
  );
}
