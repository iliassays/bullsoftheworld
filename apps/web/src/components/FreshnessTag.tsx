import { useEffect, useState } from "react";
import { api, type MarketStatus } from "../lib/api";
import { useLang } from "../lib/i18n";
import { marketUiFromConfig } from "../lib/market";
import { useTenantConfig } from "../lib/tenant";
import { formatMarketTime } from "../lib/time";

function sessionDate(iso: string | null, lang: "en" | "bn") {
  if (!iso) return "—";
  const date = new Date(`${iso.slice(0, 10)}T12:00:00Z`);
  return new Intl.DateTimeFormat(lang === "bn" ? "bn-BD" : "en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(date);
}

function scheduledTime(iso: string | null, lang: "en" | "bn", timezone: string, label: string) {
  if (!iso) return "—";
  const date = new Date(iso);
  const value = new Intl.DateTimeFormat(lang === "bn" ? "bn-BD" : "en-GB", {
    timeZone: timezone,
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
  return `${value} ${label}`;
}

export function FreshnessTag({
  asOf,
  quoteAsOf,
  detail = false,
  scope = "eod",
  priceMode = "eod",
  className = "shrink-0 ml-2",
}: {
  asOf: string | null;
  quoteAsOf?: string | null;
  detail?: boolean;
  scope?: "eod" | "mixed";
  priceMode?: "eod" | "mixed";
  className?: string;
}) {
  const { lang } = useLang();
  const { config } = useTenantConfig();
  const [status, setStatus] = useState<MarketStatus | null>(null);
  useEffect(() => {
    let active = true;
    api
      .marketStatus()
      .then((next) => active && setStatus(next))
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  if (!asOf) return null;
  const bn = lang === "bn";
  const intraday = Boolean(config.features.intraday_quotes);
  const marketOpen = status?.phase === "open";
  const delayedQuoteActive = priceMode === "mixed" && intraday && marketOpen;
  const late = Boolean(
    status?.expected_analysis_date && asOf < status.expected_analysis_date,
  );
  const sourceDate = sessionDate(asOf, lang);
  const expectedDate = sessionDate(status?.expected_analysis_date ?? null, lang);
  const nextRefresh = scheduledTime(
    status?.next_analysis_at ?? null,
    lang,
    config.timezone,
    config.timezone_label,
  );
  const priceBasis = delayedQuoteActive
    ? status?.quote_is_stale
      ? bn
        ? "ইন্ট্রাডে কোট পুরোনো; নতুন কোট না আসা পর্যন্ত দাম নির্ভরযোগ্য নয়"
        : "Intraday quote is stale; prices are unreliable until a fresh quote arrives"
      : bn
        ? `১৫ মিনিট বিলম্বিত কোট · আপডেট ${formatMarketTime(quoteAsOf, marketUiFromConfig(config))}`
        : `15-minute delayed quote · updated ${formatMarketTime(quoteAsOf, marketUiFromConfig(config))}`
    : bn
      ? `${sourceDate} সেশনের ক্লোজিং দাম ও দিনের পরিবর্তন`
      : `${sourceDate} session closing price and daily move`;

  if (!detail) {
    const compact = late
      ? bn
        ? `ডেটা দেরিতে · সর্বশেষ ${sourceDate}, প্রত্যাশিত ${expectedDate}`
        : `Data delayed · latest ${sourceDate}, expected ${expectedDate}`
      : delayedQuoteActive
        ? `${bn ? "র‍্যাঙ্কিং" : "Rankings"}: ${sourceDate} ${bn ? "ক্লোজ" : "close"} · ${priceBasis} · ${bn ? "পরবর্তী র‍্যাঙ্কিং" : "next ranking"} ${nextRefresh}`
        : `${bn ? "ডেটা" : "Data through"} ${sourceDate} ${bn ? "ক্লোজ পর্যন্ত" : "close"} · ${bn ? "পরবর্তী রিফ্রেশ" : "next refresh"} ${nextRefresh}`;
    return (
      <div className={`text-[10px] ${late || status?.quote_is_stale ? "text-down" : "text-muted"} ${className}`}>
        {compact}
      </div>
    );
  }

  return (
    <section
      className={`rounded-xl border p-3 ${late ? "border-down/40 bg-down/8" : "border-border bg-surface"} ${className}`}
      aria-label={bn ? "ডেটা আপডেটের অবস্থা" : "Data update status"}
    >
      <div className={`text-[12px] font-bold ${late ? "text-down" : "text-text"}`}>
        {late
          ? bn
            ? "ডেটা আপডেট দেরিতে হচ্ছে"
            : "Data refresh is delayed"
          : delayedQuoteActive
            ? bn
              ? "র‍্যাঙ্কিং গত ক্লোজের; দাম আজকের"
              : "Rankings use the last close; prices are today"
            : bn
              ? "সম্পূর্ণ হওয়া সেশনের গবেষণা"
              : "Completed-session research"}
      </div>
      <div className="mt-2 grid gap-1.5 text-[11px] leading-snug text-muted">
        <div>
          <b className="text-text">
            {scope === "mixed"
              ? bn
                ? "ফ্যাক্টর স্ক্রিন:"
                : "Factor screens:"
              : bn
                ? "র‍্যাঙ্কিং:"
                : "Rankings:"}
          </b>{" "}
          {sourceDate} {bn ? "ক্লোজের পরে হিসাব করা" : "close, calculated after the session"}
          {late ? ` · ${bn ? "প্রত্যাশিত" : "expected"} ${expectedDate}` : ""}
        </div>
        <div>
          <b className="text-text">{bn ? "দাম:" : "Prices:"}</b> {priceBasis}
        </div>
        <div>
          <b className="text-text">
            {delayedQuoteActive
              ? bn
                ? "পরবর্তী র‍্যাঙ্কিং হিসাব:"
                : "Next ranking calculation:"
              : bn
                ? "পরবর্তী রিফ্রেশ:"
                : "Next refresh:"}
          </b>{" "}
          {nextRefresh}
        </div>
      </div>
    </section>
  );
}
