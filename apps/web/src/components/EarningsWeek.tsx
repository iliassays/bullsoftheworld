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

// Earnings calendar — DSE board meetings called to consider results, from decoded
// announcements. Logo-first, grouped by day (Earnings-Whispers style). Two scopes:
// scope="today" (Home: just today's reporters, hidden on the many empty days) and
// scope="week" (Markets: the full trading week). Hidden entirely when nothing is scheduled.
export function EarningsWeek({ scope = "week" }: { scope?: "today" | "week" }) {
  const { t, lang } = useLang();
  const bn = lang === "bn";
  const [events, setEvents] = useState<EarningsEvent[] | null>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .earningsCalendar(scope === "today" ? 1 : 7)
      .then((e) => {
        if (!alive) return;
        if (scope === "today") {
          // "Today" means the DHAKA date (UTC+6, no DST) — plain toISOString() would show
          // yesterday's meetings to anyone browsing before 6am Dhaka.
          const today = new Date(Date.now() + 6 * 3600_000).toISOString().slice(0, 10);
          setEvents(e.filter((ev) => ev.meeting_date === today));
        } else {
          setEvents(e);
        }
      })
      .catch(() => alive && setEvents([]));
    return () => {
      alive = false;
    };
  }, [scope]);

  if (!events || events.length === 0) return null;
  const shown = expanded ? events : events.slice(0, GRID);
  const hidden = events.length - shown.length;

  // Earnings-Whispers style, turned vertical for 480px: a day header, then that day's
  // companies as a logo row — the logo is the content.
  const byDay: { date: string; items: EarningsEvent[] }[] = [];
  for (const e of shown) {
    const last = byDay[byDay.length - 1];
    if (last && last.date === e.meeting_date) last.items.push(e);
    else byDay.push({ date: e.meeting_date, items: [e] });
  }

  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <div className="flex items-center gap-2">
        <span className="text-base">📅</span>
        <span className="min-w-0 truncate text-[11px] font-bold uppercase tracking-[0.12em] text-text/90">
          {t(scope === "today" ? "home.earningsToday" : "home.earningsWeek")}
        </span>
        <span className="ml-auto shrink-0 text-[11px] font-semibold text-accent tnum">
          {events.length}
        </span>
      </div>
      {byDay.map((g) => {
        const { day, weekday } = fmt(g.date, bn);
        return (
          <div key={g.date} className="mt-3">
            <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-accent">
              {weekday} · {day}
            </div>
            <div className="mt-1.5 grid grid-cols-3 gap-2">
              {g.items.map((e) => (
                <Link
                  key={e.code}
                  to={`/s/${e.code}`}
                  className="flex flex-col items-center gap-1 rounded-xl border border-border bg-card/50 px-1.5 py-2.5 text-center hover:border-accent"
                >
                  <CompanyLogo code={e.code} size={34} />
                  <div className="w-full truncate text-[11px] font-bold">${e.code}</div>
                </Link>
              ))}
            </div>
          </div>
        );
      })}
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
