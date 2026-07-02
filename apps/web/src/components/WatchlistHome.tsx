import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Post, type SymbolDetail } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useLang } from "../lib/i18n";
import { CompanyLogo } from "./CompanyLogo";
import { Pct, taka } from "./ui";

// Personalized home section: the user's watched tickers + the latest agent note for each —
// "what changed in my stocks" at a glance. Renders nothing for logged-out / empty watchlists.
export function WatchlistHome() {
  const { user } = useAuth();
  const { t } = useLang();
  const [items, setItems] = useState<SymbolDetail[] | null>(null);
  const [noteByCode, setNoteByCode] = useState<Record<string, Post>>({});

  useEffect(() => {
    if (!user) {
      setItems(null);
      return;
    }
    api
      .watchlist()
      .then(setItems)
      .catch(() => setItems([]));
    api
      .feed(undefined, "note")
      .then((notes) => {
        const map: Record<string, Post> = {};
        for (const n of notes)
          for (const c of n.cashtags) if (!map[c]) map[c] = n;
        setNoteByCode(map);
      })
      .catch(() => {});
  }, [user]);

  if (!user || !items || items.length === 0) return null;

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between px-1">
        <div className="text-[11px] uppercase tracking-wide text-muted">
          {t("watchlist.your")}
        </div>
        <Link to="/watchlist" className="text-[11px] text-accent">
          {t("seeAll")}
        </Link>
      </div>
      {items.slice(0, 8).map(({ symbol, quote }) => {
        const note = noteByCode[symbol.code];
        return (
          <Link
            key={symbol.code}
            to={`/s/${symbol.code}`}
            className="bg-surface border border-border rounded-xl px-3 py-2.5"
          >
            <div className="flex items-center gap-2.5">
              <CompanyLogo code={symbol.code} size={30} />
              <div className="min-w-0">
                <div className="font-bold text-sm">${symbol.code}</div>
                <div className="text-xs text-muted truncate">
                  {symbol.name_en}
                </div>
              </div>
              {quote && (
                <div className="ml-auto text-right shrink-0">
                  <div className="text-sm tnum">{taka(quote.ltp)}</div>
                  <div className="text-xs font-semibold">
                    <Pct value={quote.change_pct} />
                  </div>
                </div>
              )}
            </div>
            {note && (
              <div className="text-[11px] text-accent mt-1.5 truncate">
                🤖 {note.body}
              </div>
            )}
          </Link>
        );
      })}
    </div>
  );
}
