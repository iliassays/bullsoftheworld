import { useEffect, useState } from "react";
import { CompanyLogo } from "./CompanyLogo";
import { FreshnessTag } from "./FreshnessTag";
import { Link } from "../lib/nav";
import { Empty, Pct, Spinner } from "./ui";
import { api, type DailyShortlist, type ShortlistFact } from "../lib/api";
import { type Lang, useLang } from "../lib/i18n";
import { formatMoney } from "../lib/market";

// Facts arrive structured (kind + one number) so a Bangla reader gets Bangla. `reasons`/
// `unknowns` carry the server's English rendering and are the fallback for an unknown kind —
// so a new fact kind degrades to English instead of vanishing from the row.
function renderFact(fact: ShortlistFact, lang: Lang, fallback: string | undefined): string {
  const v = fact.value;
  const n = (digits: number) => (v == null ? "" : Math.abs(v).toFixed(digits));
  if (lang !== "bn") return fallback ?? fact.kind;
  switch (fact.kind) {
    case "move":
      return v == null ? fallback ?? fact.kind : `আজ ${n(2)}% ${v >= 0 ? "বেড়েছে" : "কমেছে"}`;
    case "rel_volume":
      return `20 দিনের গড় ভলিউমের ${n(1)} গুণ লেনদেন`;
    case "near_52w_high":
      return "52-সপ্তাহের সর্বোচ্চের 3%-এর মধ্যে";
    case "range_bottom":
      return "52-সপ্তাহের রেঞ্জের নিচের 15%-এ";
    case "at_sma_200":
      return "200 দিনের গড়ের উপর দাঁড়িয়ে";
    case "pe":
      return `পি/ই ${n(1)} — সর্বশেষ বার্ষিক ইপিএস অনুযায়ী`;
    case "no_fundamentals":
      return "বার্ষিক ইপিএস/এনএভি নথিতে নেই";
    case "loss_making":
      return "সর্বশেষ বার্ষিক ইপিএস অনুযায়ী লোকসানে";
    case "negative_book":
      return "শেয়ারপ্রতি বুক ভ্যালু ঋণাত্মক";
    case "extreme_pe":
      return `পি/ই ${n(0)} — দামের তুলনায় আয় নগণ্য`;
    case "no_sma_200":
      return "200 দিনের গড় এখনও হয়নি";
    case "possible_corporate_action":
      return "বড় পতনটি কর্পোরেট অ্যাকশন হতে পারে — ডিএসই ক্লোজ অ্যাডজাস্ট করা নয়";
    default:
      return fallback ?? fact.kind;
  }
}

function formatSessionDate(value: string, lang: Lang): string {
  return new Intl.DateTimeFormat(lang === "bn" ? "bn-BD" : "en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(new Date(`${value}T12:00:00Z`));
}

function OutcomePct({ value }: { value: number }) {
  const up = value > 0;
  const down = value < 0;
  return (
    <strong className={`tnum text-sm ${up ? "text-up" : down ? "text-down" : "text-muted"}`}>
      {up ? "▲" : down ? "▼" : "•"} {Math.abs(value).toFixed(2)}%
    </strong>
  );
}

// "Today's five to look at" — the always-full research slate.
//
// Why this panel exists: the Scheme-3 board it sits above is empty on 78% of sessions (its four
// gates align on only 21.6% of them), so a researcher opening the app usually saw nothing. This
// ranks the eligible universe instead of demanding every gate pass, so it is never empty when the
// market traded.
//
// It is deliberately NOT a pick list, and the UI has to keep saying so: over 232 tested sessions
// no selection rule beat picking at random from the same pool, and a return-seeking rank did
// 1.24pp worse. So each row shows the facts that surfaced it AND what we cannot tell you, and the
// evidence footer is not dismissible. See docs/research/dse-daily-slate-study-2026-07-25.md.
export function DailyShortlistPanel({ size = 5 }: { size?: number }) {
  const { t, lang } = useLang();
  const [data, setData] = useState<DailyShortlist | null | undefined>(undefined);
  const [selectedDate, setSelectedDate] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let live = true;
    setLoading(true);
    api
      .dailyShortlist(size, selectedDate)
      .then((d) => {
        if (live) setData(d);
      })
      .catch(() => {
        if (live) setData(null);
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [selectedDate, size]);

  if (data === undefined) return <Spinner />;
  if (data === null) return <Empty>{t("shortlist.unavailable")}</Empty>;
  if (data.rows.length === 0) return <Empty>{t("scanner.empty")}</Empty>;

  const dates = data.available_dates;
  const dateIndex = dates.indexOf(data.as_of);
  const chooseDate = (value: string) => {
    setSelectedDate(value === data.latest_date ? undefined : value);
  };
  const canGoOlder = dateIndex >= 0 && dateIndex < dates.length - 1;
  const canGoNewer = dateIndex > 0;
  const historical = Boolean(data.latest_date && data.as_of !== data.latest_date);

  return (
    <section
      className={`bg-surface border border-border rounded-2xl p-4 flex flex-col gap-3 ${loading ? "opacity-70" : ""}`}
      aria-busy={loading}
    >
      <header className="flex flex-col gap-1">
        <h2 className="font-semibold text-sm">🔎 {t("shortlist.title")}</h2>
        <p className="text-xs text-muted">{t("shortlist.subtitle")}</p>
        {historical ? (
          <div className="text-[10px] text-muted">
            {lang === "bn" ? "আর্কাইভ সেশন" : "Archived session"} ·{" "}
            {formatSessionDate(data.as_of, lang)}
          </div>
        ) : (
          <FreshnessTag asOf={data.as_of} quoteAsOf={data.quote_as_of} className="mt-0.5" />
        )}
      </header>

      {dates.length > 0 && (
        <div className="grid grid-cols-[2.5rem_minmax(0,1fr)_2.5rem] items-stretch gap-2">
          <button
            type="button"
            aria-label={t("shortlist.previous")}
            title={t("shortlist.previous")}
            disabled={!canGoOlder || loading}
            onClick={() => chooseDate(dates[dateIndex + 1])}
            className="grid min-h-10 cursor-pointer place-items-center rounded-lg border border-border text-lg text-text transition hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-35"
          >
            ←
          </button>
          <label className="min-w-0">
            <span className="sr-only">{lang === "bn" ? "আর্কাইভ তারিখ" : "Archive date"}</span>
            <select
              value={data.as_of}
              aria-label={lang === "bn" ? "আর্কাইভ তারিখ" : "Archive date"}
              disabled={loading}
              onChange={(event) => chooseDate(event.target.value)}
              className="h-full min-h-10 w-full cursor-pointer rounded-lg border border-border bg-card px-2 text-center text-xs font-semibold text-text outline-none focus:border-accent disabled:cursor-wait"
            >
              {dates.map((date) => (
                <option key={date} value={date}>
                  {formatSessionDate(date, lang)}
                  {date === data.latest_date ? ` · ${t("shortlist.latest")}` : ""}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            aria-label={t("shortlist.next")}
            title={t("shortlist.next")}
            disabled={!canGoNewer || loading}
            onClick={() => chooseDate(dates[dateIndex - 1])}
            className="grid min-h-10 cursor-pointer place-items-center rounded-lg border border-border text-lg text-text transition hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-35"
          >
            →
          </button>
        </div>
      )}

      {data.evidence_mode === "reconstructed" && (
        <p className="rounded-lg border border-accent/30 bg-accent/8 px-3 py-2 text-[11px] leading-relaxed text-muted">
          {t("shortlist.reconstructed")}
        </p>
      )}

      <div className="grid gap-1 text-[11px] leading-relaxed text-muted">
        <p>{t("shortlist.eligible").replace("{n}", String(data.eligible_names))}</p>
        <p>{t("shortlist.source")}</p>
      </div>

      <ol className="flex flex-col gap-2">
        {data.rows.map((row) => {
          // Some DSE rows carry name_en equal to the code; showing both reads as a stutter.
          const raw = (lang === "bn" ? row.name_bn : row.name_en) || row.name_en || "";
          const name = raw.toUpperCase() === row.code.toUpperCase() ? "" : raw;
          return (
            <li key={row.code} className="border border-border rounded-xl p-3">
              <div className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2">
                <div className="flex items-center gap-2">
                  <span className="w-4 shrink-0 text-xs text-muted">{row.rank}</span>
                  <CompanyLogo code={row.code} size={28} />
                </div>
                <div className="min-w-0">
                  <Link to={`/s/${row.code}`} className="block truncate text-sm font-semibold">
                    {row.code}
                  </Link>
                  {name && <div className="truncate text-[11px] text-muted">{name}</div>}
                </div>
                <div className="shrink-0 text-right">
                  <div className="text-sm tabular-nums">{formatMoney(row.close)}</div>
                  {row.change_pct != null && <Pct value={row.change_pct} />}
                </div>
              </div>

              {row.facts.length > 0 && (
                <ul className="mt-2 flex flex-col gap-0.5">
                  {row.facts.map((fact, i) => (
                    <li key={fact.kind} className="text-xs text-muted">
                      · {renderFact(fact, lang, row.reasons[i])}
                    </li>
                  ))}
                </ul>
              )}

              {/* Omit-over-mislead: the gaps are shown on the row, never quietly dropped. */}
              {row.cautions.length > 0 && (
                <ul className="mt-1.5 flex flex-col gap-0.5">
                  {row.cautions.map((caution, i) => (
                    <li key={caution.kind} className="text-xs text-down">
                      ⚠ {renderFact(caution, lang, row.unknowns[i])}
                    </li>
                  ))}
                </ul>
              )}

              <div className="mt-2 grid grid-cols-2 gap-2 border-t border-border pt-2">
                <div className="min-w-0">
                  <div className="text-[10px] text-muted">{t("shortlist.latestReturn")}</div>
                  {row.return_since_pct == null ? (
                    <div className="mt-0.5 text-[11px] text-muted">{t("shortlist.noOutcome")}</div>
                  ) : (
                    <OutcomePct value={row.return_since_pct} />
                  )}
                </div>
                <div className="min-w-0">
                  <div className="text-[10px] text-muted">{t("shortlist.peakMove")}</div>
                  {row.max_went_pct == null ? (
                    <div className="mt-0.5 text-[11px] text-muted">{t("shortlist.noOutcome")}</div>
                  ) : (
                    <OutcomePct value={row.max_went_pct} />
                  )}
                </div>
              </div>
              {row.sessions_since > 0 && (
                <div className="mt-1 text-[10px] text-muted">
                  {row.sessions_since} {t("shortlist.sessions")}
                  {row.outcome_as_of
                    ? ` · ${lang === "bn" ? "ফলাফল" : "outcome through"} ${formatSessionDate(row.outcome_as_of, lang)}`
                    : ""}
                </div>
              )}
            </li>
          );
        })}
      </ol>

      {/* Not dismissible and not behind a tooltip: the measured base rate is the honest frame. */}
      <p className="text-[11px] text-muted border-t border-border pt-2">
        {t("shortlist.evidence")}
      </p>
      {dates.length > 0 && (
        <p className="text-[10px] leading-relaxed text-muted">{t("shortlist.outcomeCaveat")}</p>
      )}
    </section>
  );
}
