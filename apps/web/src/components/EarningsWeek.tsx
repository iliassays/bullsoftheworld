import { useEffect, useState } from "react";
import { Link } from "../lib/nav";
import { api, type EarningsEvent } from "../lib/api";
import { useLang } from "../lib/i18n";
import { useTenantConfig } from "../lib/tenant";
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
  const { config } = useTenantConfig();
  const bn = lang === "bn";
  const [events, setEvents] = useState<EarningsEvent[] | null>(null);
  const [expanded, setExpanded] = useState(false);

  const todayParts = Object.fromEntries(
    new Intl.DateTimeFormat("en-US", {
      timeZone: config.timezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    })
      .formatToParts(new Date())
      .map((part) => [part.type, part.value]),
  );
  const marketToday = `${todayParts.year}-${todayParts.month}-${todayParts.day}`;
  const marketDate = new Date(`${marketToday}T00:00:00Z`);
  const dow = marketDate.getUTCDay();
  const toWeekStart =
    config.market === "DSE"
      ? dow === 5
        ? 2
        : dow === 6
          ? 1
          : -dow
      : dow === 6
        ? 2
        : dow === 0
          ? 1
          : 1 - dow;
  const weekStart = new Date(marketDate.getTime() + toWeekStart * 86_400_000);
  const weekDates = Array.from({ length: 5 }, (_, i) =>
    new Date(weekStart.getTime() + i * 86_400_000).toISOString().slice(0, 10),
  );

  useEffect(() => {
    let alive = true;
    const back = scope === "week" ? Math.max(0, -toWeekStart) : 0;
    api
      .earningsCalendar(scope === "today" ? 1 : 7, back, scope === "today" ? 9 : 4)
      .then((e) => {
        if (!alive) return;
        setEvents(
          scope === "today" ? e.filter((ev) => ev.meeting_date === marketToday) : e,
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
    const estimated = config.features.sec_filings;
    return (
      <div className="bg-surface border border-border rounded-2xl p-3">
        <div className="mb-3">
          <div className="text-sm font-semibold text-text">
            {estimated
              ? bn
                ? "আনুমানিক রিপোর্টিং সময়"
                : "Estimated reporting windows"
              : t("home.earningsWeek")}
          </div>
          <p className="mt-0.5 text-[10px] leading-relaxed text-muted">
            {estimated
              ? bn
                ? "আগের SEC ফাইলিংয়ের সময়সূচি থেকে অনুমান; কোম্পানি নিশ্চিত করেনি।"
                : "Estimated from prior SEC filing cadence; these are not company-confirmed earnings dates."
              : t("home.earningsWeekNote")}
          </p>
        </div>
        <div className="overflow-hidden rounded-xl border border-border bg-card/25">
          {weekDates.map((iso) => {
            const { day, weekday } = fmt(iso, bn);
            const items = events.filter((e) => e.meeting_date === iso);
            const total = items[0]?.day_total ?? items.length;
            const past = iso < marketToday;
            return (
              <div
                key={iso}
                className={`grid grid-cols-[3.75rem_minmax(0,1fr)] gap-3 border-t border-border px-3 py-3 first:border-t-0 ${past ? "opacity-55" : ""}`}
              >
                <div className="text-[10px] font-bold uppercase tracking-[0.1em] text-accent">
                  {weekday}
                  <div className="mt-0.5 text-[10px] font-semibold normal-case tracking-normal text-muted">
                    {day}
                  </div>
                </div>
                <div className="min-w-0">
                  <div className="flex min-h-5 flex-wrap items-center gap-x-3 gap-y-1.5">
                    {items.slice(0, 3).map((e) => (
                      <Link
                        key={e.code}
                        to={`/s/${e.code}`}
                        title={e.name_en}
                        className="inline-flex min-w-0 items-center gap-1.5 text-[11px] font-bold hover:text-accent"
                      >
                        <CompanyLogo code={e.code} size={18} />
                        <span className="whitespace-nowrap">
                          {e.status === "estimated" ? "~" : ""}${e.code}
                        </span>
                      </Link>
                    ))}
                    {total === 0 && (
                      <span className="text-[10px] text-muted">
                        {bn ? "কোনো সময়সূচি নেই" : "No reporting window"}
                      </span>
                    )}
                  </div>
                  {total > 0 && (
                    <div className="mt-1 text-[9px] leading-snug text-muted">
                      {estimated
                        ? bn
                          ? `${total}টি আনুমানিক উইন্ডোর মধ্যে ${items.slice(0, 3).length}টি দেখানো হয়েছে`
                          : `Showing ${items.slice(0, 3).length} of ${total} estimated windows`
                        : bn
                          ? `${total}টি ঘোষিত সভা`
                          : `${total} announced ${total === 1 ? "meeting" : "meetings"}`}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
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
          {events[0]?.day_total ?? events.length}
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
                  <div className="w-full truncate text-[11px] font-bold">
                    {e.status === "estimated" ? "~" : ""}${e.code}
                  </div>
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
      <p className="text-[10px] text-muted mt-2.5">
        {config.features.sec_filings
          ? bn
            ? "~ তারিখটি আগের SEC ফাইলিংয়ের সময়সূচি থেকে অনুমান; কোম্পানি নিশ্চিত করেনি।"
            : "~ Date estimated from prior SEC filing cadence; not company-confirmed."
          : t("home.earningsWeekNote")}
      </p>
    </div>
  );
}
