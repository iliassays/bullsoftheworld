import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Quote } from "../lib/api";
import { Pct, Spinner, taka } from "../components/ui";

export function Markets() {
  const [quotes, setQuotes] = useState<Quote[] | null>(null);
  const [q, setQ] = useState("");

  useEffect(() => {
    api.quotes().then(setQuotes).catch(() => setQuotes([]));
  }, []);

  const filtered = useMemo(
    () => (quotes ?? []).filter((x) => x.code.includes(q.toUpperCase())),
    [quotes, q],
  );

  if (quotes === null) return <Spinner />;

  return (
    <div className="flex flex-col gap-2">
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search code, e.g. GP"
        className="bg-surface border border-border rounded-xl px-3 py-2 text-sm outline-none focus:border-accent"
      />
      <div className="text-[11px] uppercase tracking-wide text-muted px-1 mt-1">Top movers</div>
      {filtered.map((x) => (
        <Link
          key={x.code}
          to={`/s/${x.code}`}
          className="flex items-center bg-surface border border-border rounded-xl px-3 py-2.5"
        >
          <div className="font-bold text-sm">${x.code}</div>
          <div className="ml-auto text-right">
            <div className="text-sm tnum">{taka(x.ltp)}</div>
            <div className="text-xs font-semibold">
              <Pct value={x.change_pct} />
            </div>
          </div>
        </Link>
      ))}
    </div>
  );
}
