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

const GRID = 9; // 3×3 by default; "+N more" expands the rest

// This week's earnings — DSE board meetings called to consider results, from decoded
// announcements. A compact logo grid (3 across): who reports, and when. Descriptive heads-up
// only; hidden entirely when nothing is scheduled.
export function EarningsWeek() {
  const { t, lang } = useLang();
  const bn = lang === "bn";
  const [events, setEvents] = useState<EarningsEvent[] | null>(null);
  const [expanded, setExpanded] = useState(false);

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
  const shown = expanded ? events : events.slice(0, GRID);
  const hidden = events.length - shown.length;

  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <div className="flex items-center gap-2">
        <span className="text-base">📅</span>
        <span className="min-w-0 truncate text-[11px] font-bold uppercase tracking-[0.12em] text-text/90">
          {t("home.earningsWeek")}
        </span>
        <span className="ml-auto shrink-0 text-[11px] font-semibold text-accent tnum">
          {events.length}
        </span>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2">
        {shown.map((e) => {
          const { day, weekday } = fmt(e.meeting_date, bn);
          return (
            <Link
              key={`${e.code}-${e.meeting_date}`}
              to={`/s/${e.code}`}
              className="flex flex-col items-center gap-1 rounded-xl border border-border bg-card/50 px-1.5 py-2.5 text-center hover:border-accent"
            >
              <CompanyLogo code={e.code} size={30} />
              <div className="w-full truncate text-[11px] font-bold">${e.code}</div>
              <div className="text-[10px] text-accent font-semibold tnum">
                {weekday} · {day}
              </div>
            </Link>
          );
        })}
      </div>
      {hidden > 0 && (
        <button
          onClick={() => setExpanded(true)}
          className="mt-2 w-full rounded-xl border border-border py-1.5 text-[11px] font-semibold text-muted hover:border-accent hover:text-accent"
        >
          +{hidden} {bn ? "আরও" : "more"}
        </button>
      )}
      <p className="text-[10px] text-muted mt-2.5">{t("home.earningsWeekNote")}</p>
    </div>
  );
}
