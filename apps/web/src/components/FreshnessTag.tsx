import { useLang } from "../lib/i18n";
import { formatDhakaTime } from "../lib/time";

// DSE trades Sun–Thu, 10:00–14:30 BDT (04:00–08:30 UTC); +buffer for the last delayed snapshot.
function marketLive(): boolean {
  const now = new Date();
  const utcMin = now.getUTCHours() * 60 + now.getUTCMinutes();
  const dhakaDay = new Date(now.getTime() + 6 * 3600_000).getUTCDay(); // 0=Sun … 6=Sat
  return dhakaDay <= 4 && utcMin >= 4 * 60 && utcMin <= 8 * 60 + 45;
}

// One honest freshness signal (no per-widget badges): during the session show a live dot + the
// real last-quote time; after the close show the close date. Kills "is this live or yesterday?".
//
// Shared by every page built on /screens (Markets, Ideas) — the RANKINGS on those boards are
// EOD-analytics-anchored (`asOf`, refreshed once daily after close) even on days the market is
// currently open; only the raw quote prices track `quoteAsOf` (the 15-min poll). A user asked
// (2026-07-05) why a board's price+% looked unlabeled/ambiguous — the real gap wasn't the %
// label, it was this anchor being shown on Markets but missing entirely on Ideas.
export function FreshnessTag({
  asOf,
  quoteAsOf,
  className = "shrink-0 ml-2",
}: {
  asOf: string | null;
  quoteAsOf?: string | null;
  className?: string;
}) {
  const { t } = useLang();
  const live = marketLive();
  if (live && quoteAsOf) {
    const time = formatDhakaTime(quoteAsOf);
    return (
      <div className={`text-[10px] text-muted flex items-center gap-1 ${className}`}>
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-up animate-pulse" />
        {t("mkt.live")} · {t("delayed")} · {t("mkt.updated")} {time}
      </div>
    );
  }
  if (!asOf) return null;
  return (
    <div className={`text-[10px] text-muted ${className}`}>
      {t("asOf")} {asOf} {t("close")}
    </div>
  );
}
