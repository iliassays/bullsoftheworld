import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Quote } from "../lib/api";
import { useLang } from "../lib/i18n";
import { formatDhakaTime } from "../lib/time";
import { Pct, taka } from "./ui";

// DSE trades Sun–Thu, 10:00–14:30 BDT (= 04:00–08:30 UTC). During that window the strip refreshes
// often so the top bar reflects the live (delayed) session; otherwise it's the EOD snapshot.
function inMarketHours(): boolean {
  const now = new Date();
  const utcMin = now.getUTCHours() * 60 + now.getUTCMinutes();
  const dhakaDay = new Date(now.getTime() + 6 * 3600_000).getUTCDay(); // 0=Sun … 6=Sat
  const tradingDay = dhakaDay <= 4; // Sun–Thu
  return tradingDay && utcMin >= 4 * 60 && utcMin <= 8 * 60 + 45; // ~10:00–14:45 BDT (+buffer)
}

export function TickerStrip() {
  const { t } = useLang();
  const [quotes, setQuotes] = useState<Quote[]>([]);

  useEffect(() => {
    let alive = true;
    const load = () =>
      api.quotes().then((q) => alive && setQuotes(q.slice(0, 12))).catch(() => {});
    load();
    // Refresh every 60s during market hours so the top bar never sits stale; a slow 10-min
    // heartbeat otherwise so it self-heals right after the open without hammering the API overnight.
    const id = setInterval(load, inMarketHours() ? 60_000 : 600_000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  if (!quotes.length) return null;
  const asOf = quotes[0]?.as_of;
  const asOfTime = asOf ? formatDhakaTime(asOf) : null;
  const live = inMarketHours();
  return (
    <div className="flex flex-col gap-1">
      {asOfTime && (
        <div className="flex items-center gap-1.5 px-1 text-[10px] text-muted">
          <span
            className={`inline-block w-1.5 h-1.5 rounded-full ${live ? "bg-up animate-pulse" : "bg-muted"}`}
          />
          {t("asOf")} {asOfTime}
        </div>
      )}
      <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1 [scrollbar-width:none]">
        {quotes.map((q) => (
          <Link
            key={q.code}
            to={`/s/${q.code}`}
            className="shrink-0 min-w-[104px] bg-card border border-border rounded-xl px-3 py-2"
          >
            <div className="font-bold text-[13px]">${q.code}</div>
            <div className="text-xs text-muted tnum">{taka(q.ltp)}</div>
            <div className="text-xs font-semibold mt-0.5">
              <Pct value={q.change_pct} />
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
