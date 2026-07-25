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

  useEffect(() => {
    let live = true;
    api
      .dailyShortlist(size)
      .then((d) => live && setData(d))
      .catch(() => live && setData(null));
    return () => {
      live = false;
    };
  }, [size]);

  if (data === undefined) return <Spinner />;
  if (data === null) return <Empty>{t("shortlist.unavailable")}</Empty>;
  if (data.rows.length === 0) return <Empty>{t("scanner.empty")}</Empty>;

  return (
    <div className="bg-surface border border-border rounded-2xl p-4 flex flex-col gap-3">
      <div className="flex items-start gap-2">
        <div className="min-w-0">
          <div className="font-semibold text-sm">🔎 {t("shortlist.title")}</div>
          <div className="text-xs text-muted mt-0.5">{t("shortlist.subtitle")}</div>
        </div>
        <FreshnessTag asOf={data.as_of} quoteAsOf={data.quote_as_of} />
      </div>

      <div className="text-[11px] text-muted">
        {t("shortlist.eligible").replace("{n}", String(data.eligible_names))}
      </div>

      <ol className="flex flex-col gap-2">
        {data.rows.map((row) => {
          // Some DSE rows carry name_en equal to the code; showing both reads as a stutter.
          const raw = (lang === "bn" ? row.name_bn : row.name_en) || row.name_en || "";
          const name = raw.toUpperCase() === row.code.toUpperCase() ? "" : raw;
          return (
            <li key={row.code} className="border border-border rounded-xl p-3">
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted w-4 shrink-0">{row.rank}</span>
                <CompanyLogo code={row.code} size={24} />
                <Link to={`/s/${row.code}`} className="font-semibold text-sm truncate">
                  {row.code}
                </Link>
                <span className="text-xs text-muted truncate min-w-0">{name}</span>
                <span className="ml-auto shrink-0 text-sm tabular-nums">
                  {formatMoney(row.close)}
                </span>
                {row.change_pct != null && <Pct value={row.change_pct} />}
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
            </li>
          );
        })}
      </ol>

      {/* Not dismissible and not behind a tooltip: the measured base rate is the honest frame. */}
      <p className="text-[11px] text-muted border-t border-border pt-2">
        {t("shortlist.evidence")}
      </p>
    </div>
  );
}
