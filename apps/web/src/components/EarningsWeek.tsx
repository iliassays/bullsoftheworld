import { useEffect, useState } from "react";
import { Link } from "../lib/nav";
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

  // All dates in DHAKA time (UTC+6, no DST) — plain toISOString() would show yesterday
  // to anyone browsing before 6am Dhaka.
  const dhakaNow = new Date(Date.now() + 6 * 3600_000);
  const dhakaToday = dhakaNow.toISOString().slice(0, 10);
  // The DSE week runs Sun–Thu. On Fri/Sat, show the coming week; otherwise the current one.
  const dow = dhakaNow.getUTCDay(); // 0=Sun … 6=Sat
  const toSunday = dow === 5 ? 2 : dow === 6 ? 1 : -dow;
  const weekStart = new Date(dhakaNow.getTime() + toSunday * 86_400_000);
  const weekDates = Array.from({ length: 5 }, (_, i) =>
    new Date(weekStart.getTime() + i * 86_400_000).toISOString().slice(0, 10),
  );

  useEffect(() => {
    let alive = true;
    const back = scope === "week" ? Math.max(0, -toSunday) : 0;
    api
      .earningsCalendar(scope === "today" ? 1 : 7, back)
      .then((e) => {
        if (!alive) return;
        setEvents(
          scope === "today" ? e.filter((ev) => ev.meeting_date === dhakaToday) : e,
        );
      })
      .catch(() => alive && setEvents([]));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope]);

  if (!events) return null;
  // A DSE day with zero earnings meetings is the common case (results cluster into a handful of
  // weeks a year) — going fully silent here made the whole feature invisible most days (2026-07-04
  // user report: "where is earnings today?"). Stay present with a way to see the fuller picture.
  if (scope === "today" && events.length === 0)
    return (
      <Link
        to="/markets"
        className="bg-surface border border-border rounded-2xl px-4 py-3 flex items-center justify-between hover:border-accent"
      >
        <span className="text-sm text-muted">📅 {t("home.earningsTodayEmpty")}</span>
        <span className="text-xs font-semibold text-accent shrink-0">{t("home.earningsWeek")} →</span>
      </Link>
    );

  if (scope === "week") {
    // Earnings-Whispers calendar: five fixed Sun–Thu columns. Empty columns stay empty —
    // an almost-blank week honestly LOOKS almost blank.
    return (
      <div className="bg-surface border border-border rounded-2xl p-3">
        <div className="grid grid-cols-5 divide-x divide-border/50">
          {weekDates.map((iso) => {
            const { day, weekday } = fmt(iso, bn);
            const items = events.filter((e) => e.meeting_date === iso);
            const past = iso < dhakaToday;
            return (
              <div key={iso} className={`px-1 ${past ? "opacity-50" : ""}`}>
                <div className="text-center text-[9px] font-bold uppercase tracking-[0.1em] text-accent leading-tight">
                  {weekday}
                  <div className="text-[9px] font-semibold text-muted normal-case tracking-normal">{day}</div>
                </div>
                <div className="mt-2 flex flex-col items-center gap-2.5 min-h-[56px]">
                  {items.map((e) => (
                    <Link
                      key={e.code}
                      to={`/s/${e.code}`}
                      className="flex w-full flex-col items-center gap-0.5"
                    >
                      <CompanyLogo code={e.code} size={30} />
                      <span className="w-full truncate text-center text-[8px] font-bold leading-tight">
                        {e.code}
                      </span>
                    </Link>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
        <p className="text-[10px] text-muted mt-2 text-center">{t("home.earningsWeekNote")}</p>
      </div>
    );
  }

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
