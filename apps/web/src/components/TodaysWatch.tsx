import { useEffect, useState } from "react";
import { Link } from "../lib/nav";
import { api, type Breadth, type MarketSession, type TodaysWatch as TodaysWatchT } from "../lib/api";
import { trackProductEvent } from "../lib/analytics";
import { useLang } from "../lib/i18n";
import { useTenantConfig } from "../lib/tenant";

// Heading comes from the server-computed market session (tenant timezone) — not hardcoded here.
const SESSION: Record<MarketSession, { key: string; icon: string }> = {
  pre_open: { key: "session.pre_open", icon: "🌅" },
  open: { key: "session.open", icon: "☀️" },
  post_close: { key: "session.post_close", icon: "🌙" },
  weekend: { key: "session.weekend", icon: "📅" },
};

function BreadthBar({ b }: { b: Breadth }) {
  const { t, lang } = useLang();
  const { config } = useTenantConfig();
  const traded = b.advancers + b.decliners + b.unchanged || 1;
  const up = (b.advancers / traded) * 100;
  const flat = (b.unchanged / traded) * 100;
  return (
    <div className="mt-3">
      <div className="flex justify-between text-[11px] mb-1">
        <span className="text-up tnum">▲ {b.advancers}</span>
        <span className="text-muted tnum">{b.unchanged} {t("watch.flat")}</span>
        <span className="text-down tnum">{b.decliners} ▼</span>
      </div>
      <div className="flex h-1.5 rounded-full overflow-hidden bg-card">
        <div className="bg-up" style={{ width: `${up}%` }} />
        <div className="bg-muted/40" style={{ width: `${flat}%` }} />
        <div className="bg-down flex-1" />
      </div>
      <p className="mt-1 text-[10px] text-muted">
        {config.market === "US"
          ? lang === "bn"
            ? `প্রকাশিত ${b.total}টি মার্কিন শেয়ারের ট্র্যাক করা ব্রেডথ; পুরো মার্কিন বাজার নয়।`
            : `Tracked breadth across ${b.total} published U.S. stocks, not the whole U.S. market.`
          : lang === "bn"
            ? `${b.total}টি DSE তালিকাভুক্ত শেয়ারের ব্রেডথ।`
            : `Breadth across ${b.total} DSE listings.`}
      </p>
    </div>
  );
}

// AI daily brief — session-aware heading + market breadth + clickable movers/chatter chips.
export function TodaysWatch() {
  const { t, lang } = useLang();
  const [data, setData] = useState<TodaysWatchT | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api
      .todaysWatch()
      .then((d) => alive && setData(d))
      .catch(() => {})
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, []);

  // Loading skeleton so the panel is always visible while the (slow) first AI call runs.
  if (loading && !data) {
    return (
      <div className="bg-surface border border-border rounded-2xl p-4">
        <div className="font-semibold text-sm">📋 {t("session.default")}</div>
        <p className="text-muted text-sm mt-2">{t("digest.loading")}</p>
      </div>
    );
  }

  if (!data) return null;
  const heading = SESSION[data.session] ?? { key: "session.default", icon: "📋" };

  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <div className="font-semibold text-sm">
        {heading.icon} {t(heading.key)}
      </div>
      {data.breadth && data.breadth.total > 0 && <BreadthBar b={data.breadth} />}
      {data.summary && (
        <p className="text-[15px] leading-relaxed mt-3 text-text/90">{data.summary}</p>
      )}
      {!!data.personal?.length && (
        <div className="mt-3 border-t border-border/60 pt-2.5">
          <div className="text-[10px] font-bold uppercase tracking-wide text-muted">
            {lang === "bn" ? "আপনার তালিকায় পরিবর্তন" : "Your watchlist changed"}
          </div>
          <div className="mt-1 flex flex-col">
            {data.personal.map((item, index) => (
              <Link
                key={`${item.kind}:${item.code ?? "market"}:${index}`}
                to={item.code ? `/s/${item.code}` : "/alerts"}
                onClick={() =>
                  trackProductEvent("open_home_alert", {
                    alert_kind: item.kind,
                    stock_code: item.code,
                  })
                }
                className="flex items-center gap-2 border-t border-border/40 py-2 text-xs first:border-t-0"
              >
                <span aria-hidden>{item.kind === "filing" ? "📄" : item.kind === "ownership" ? "🏛️" : "🔔"}</span>
                <span className="min-w-0 flex-1 line-clamp-2">{item.title}</span>
                <span className="text-accent">→</span>
              </Link>
            ))}
          </div>
        </div>
      )}
      {!!data.research?.length && (
        <div className="mt-3 border-t border-border/60 pt-2.5">
          <div className="flex items-center justify-between">
            <div className="text-[10px] font-bold uppercase tracking-wide text-muted">
              {lang === "bn" ? "এরপর গবেষণা করুন" : "Research next"}
            </div>
            <Link to="/ideas" className="text-[10px] font-semibold text-accent">
              {lang === "bn" ? "সব আইডিয়া" : "All ideas"} →
            </Link>
          </div>
          <div className="mt-1 flex flex-col">
            {data.research.slice(0, 3).map((item) => (
              <Link
                key={`${item.board_key}:${item.code}`}
                to={`/s/${item.code}`}
                onClick={() =>
                  trackProductEvent("open_home_research", {
                    board_key: item.board_key,
                    stock_code: item.code,
                  })
                }
                className="flex items-center gap-2.5 border-t border-border/40 py-2 first:border-t-0"
              >
                <span className="text-xs font-extrabold">${item.code}</span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[10px] font-semibold text-accent">{item.board_title}</span>
                  <span className="block truncate text-[11px] text-muted">{item.reason}</span>
                </span>
                <span className="text-accent">→</span>
              </Link>
            ))}
          </div>
        </div>
      )}
      {data.items.length > 0 && (
        <div className="flex gap-1.5 flex-wrap mt-3">
          {data.items.slice(0, 8).map((it) => (
            <Link
              key={it.code}
              to={`/s/${it.code}`}
              className="text-xs bg-card border border-border rounded-full px-2.5 py-1"
            >
              ${it.code}{" "}
              <span className={`tnum ${it.change_pct >= 0 ? "text-up" : "text-down"}`}>
                {it.change_pct >= 0 ? "+" : ""}
                {it.change_pct.toFixed(1)}%
              </span>
              {it.posts > 0 && <span className="text-muted"> · {it.posts}💬</span>}
            </Link>
          ))}
        </div>
      )}
      <p className="text-[10px] text-muted mt-2">{t("watch.aiFooter")}</p>
    </div>
  );
}
