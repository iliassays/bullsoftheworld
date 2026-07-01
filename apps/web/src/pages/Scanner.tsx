import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type ScannerResponse, type Screen } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useLang } from "../lib/i18n";
import { Empty, Pct, Spinner, taka } from "../components/ui";
import { Watchlist } from "./Watchlist";

type Tab = "today" | "value" | "watchlist";

const BOARD_ICON: Record<string, string> = {
  quality_reversal: "🌊",
  active_today: "🔥",
  most_active: "💸",
  value_vs_sector: "⭐",
  dividend_yield: "💵",
};

function BoardCard({ board }: { board: Screen }) {
  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <div className="font-semibold text-sm">
        {BOARD_ICON[board.key] ?? "📈"} {board.title}
      </div>
      <p className="text-xs text-muted mt-0.5 leading-relaxed">{board.description}</p>
      <div className="mt-2 flex flex-col divide-y divide-border">
        {board.items.map((it) => (
          <Link
            key={it.code}
            to={`/s/${it.code}`}
            className="flex items-start gap-3 py-2.5"
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-bold text-[13px]">${it.code}</span>
                {it.category && (
                  <span className="text-[10px] text-muted">Cat {it.category}</span>
                )}
              </div>
              {it.why && (
                <div className="text-[11px] text-muted leading-snug mt-0.5">{it.why}</div>
              )}
            </div>
            <div className="text-right shrink-0 tnum">
              {it.last_close > 0 && (
                <div className="text-[13px] font-semibold">{taka(it.last_close)}</div>
              )}
              <div className="text-xs font-semibold">
                {it.change_1d != null ? (
                  <Pct value={it.change_1d} />
                ) : (
                  <span className="text-muted">
                    {it.value}
                    {board.value_label.includes("%") ? "%" : ""}
                  </span>
                )}
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

function Boards({ tab, watched }: { tab: "today" | "value"; watched: boolean }) {
  const { t } = useLang();
  const [data, setData] = useState<ScannerResponse | null>(null);
  useEffect(() => {
    setData(null);
    let live = true;
    api
      .scannerRadar(tab, watched)
      .then((d) => live && setData(d))
      .catch(() => live && setData(null));
    return () => {
      live = false;
    };
  }, [tab, watched]);

  if (!data) return <Spinner />;
  if (data.boards.length === 0)
    return (
      <Empty>{watched ? t("scanner.emptyWatched") : t("scanner.empty")}</Empty>
    );
  return (
    <div className="flex flex-col gap-3">
      {data.boards.map((b) => (
        <BoardCard key={b.key} board={b} />
      ))}
    </div>
  );
}

export function Scanner() {
  const { t } = useLang();
  const { user } = useAuth();
  const [tab, setTab] = useState<Tab>("today");
  const [watched, setWatched] = useState(false);

  const seg = (id: Tab, label: string) => (
    <button
      onClick={() => setTab(id)}
      className={`flex-1 rounded-full py-1.5 text-sm font-semibold transition ${
        tab === id ? "bg-accent text-bg" : "text-muted"
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="flex flex-col gap-3">
      <div className="flex gap-1 bg-surface border border-border rounded-full p-1">
        {seg("today", t("scanner.today"))}
        {seg("value", t("scanner.value"))}
        {seg("watchlist", t("scanner.watchlist"))}
      </div>

      {tab === "watchlist" ? (
        <Watchlist />
      ) : (
        <>
          {user && (
            <div className="flex items-center gap-2 text-xs">
              <span className="text-muted">{t("scanner.scope")}:</span>
              <button
                onClick={() => setWatched(false)}
                className={`rounded-full px-3 py-1 border ${!watched ? "border-accent text-accent" : "border-border text-muted"}`}
              >
                {t("scanner.market")}
              </button>
              <button
                onClick={() => setWatched(true)}
                className={`rounded-full px-3 py-1 border ${watched ? "border-accent text-accent" : "border-border text-muted"}`}
              >
                ⭐ {t("scanner.watched")}
              </button>
            </div>
          )}
          <Boards tab={tab} watched={watched && !!user} />
        </>
      )}
    </div>
  );
}
