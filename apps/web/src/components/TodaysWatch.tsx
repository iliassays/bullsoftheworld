import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Breadth, type MarketSession, type TodaysWatch as TodaysWatchT } from "../lib/api";
import { useLang } from "../lib/i18n";

// Heading comes from the server-computed market session (tenant timezone) — not hardcoded here.
const SESSION: Record<MarketSession, { key: string; icon: string }> = {
  pre_open: { key: "session.pre_open", icon: "🌅" },
  open: { key: "session.open", icon: "☀️" },
  post_close: { key: "session.post_close", icon: "🌙" },
  weekend: { key: "session.weekend", icon: "📅" },
};

function BreadthBar({ b }: { b: Breadth }) {
  const { t } = useLang();
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
    </div>
  );
}

// AI daily brief — session-aware heading + market breadth + clickable movers/chatter chips.
export function TodaysWatch() {
  const { t } = useLang();
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
