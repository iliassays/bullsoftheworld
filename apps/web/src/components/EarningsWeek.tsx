import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type EarningsEvent } from "../lib/api";
import { useLang } from "../lib/i18n";
import { CompanyLogo } from "./CompanyLogo";

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

  // Group by meeting date (API returns them nearest-first) so the card reads like an agenda: a day
  // header, then the companies reporting that day — clean when sparse, scalable when a week is busy.
  const groups: { date: string; items: EarningsEvent[] }[] = [];
  for (const e of events) {
    const last = groups[groups.length - 1];
    if (last && last.date === e.meeting_date) last.items.push(e);
    else groups.push({ date: e.meeting_date, items: [e] });
  }

  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <div className="font-semibold text-sm">📅 {t("home.earningsWeek")}</div>
      <p className="text-[12px] text-muted mt-0.5 leading-snug">{t("home.earningsWeekSub")}</p>
      <div className="mt-1">
        {groups.map((g) => {
          const { day, weekday } = fmt(g.date, bn);
          return (
            <div key={g.date} className="mt-3">
              <div className="text-[12px] font-semibold text-accent mb-2">
                {weekday} · {day}
              </div>
              <div className="flex flex-col gap-2.5">
                {g.items.map((e) => {
                  const period = e.period ? t(`news.period.${e.period}`) : "";
                  // name_en falls back to the code for un-enriched symbols; skip the sub-line then
                  // so we don't print the ticker twice.
                  const name = (bn && e.name_bn) || e.name_en;
                  const showName = !!name && name !== e.code;
                  return (
                    <Link key={e.code} to={`/s/${e.code}`} className="flex items-center gap-3">
                      <CompanyLogo code={e.code} />
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-semibold">${e.code}</div>
                        {showName && (
                          <div className="text-[11px] text-muted truncate">{name}</div>
                        )}
                      </div>
                      {period && <div className="text-[11px] text-muted flex-none">{period}</div>}
                    </Link>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
      <p className="text-[10px] text-muted mt-3">{t("home.earningsWeekNote")}</p>
    </div>
  );
}
