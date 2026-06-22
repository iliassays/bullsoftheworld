import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Quote } from "../lib/api";
import { Pct, taka } from "./ui";

export function TickerStrip() {
  const [quotes, setQuotes] = useState<Quote[]>([]);
  useEffect(() => {
    api.quotes().then((q) => setQuotes(q.slice(0, 12))).catch(() => {});
  }, []);
  if (!quotes.length) return null;
  return (
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
  );
}
