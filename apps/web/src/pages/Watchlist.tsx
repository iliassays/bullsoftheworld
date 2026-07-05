import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type SymbolDetail } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useLang } from "../lib/i18n";
import { CompanyLogo } from "../components/CompanyLogo";
import { Empty, Pct, Spinner, taka } from "../components/ui";

export function Watchlist() {
  const { user } = useAuth();
  const { t } = useLang();
  const [items, setItems] = useState<SymbolDetail[] | null>(null);

  useEffect(() => {
    if (user) api.watchlist().then(setItems).catch(() => setItems([]));
  }, [user]);

  if (!user)
    return (
      <Empty>
        <Link to="/me" className="text-accent">
          {t("common.login")}
        </Link>{" "}
        {t("wl.toBuild")}
      </Empty>
    );
  if (items === null) return <Spinner />;
  if (items.length === 0) return <Empty>{t("wl.empty")}</Empty>;

  return (
    <div className="flex flex-col gap-2">
      {items.map(({ symbol, quote }) => (
        <Link
          key={symbol.code}
          to={`/s/${symbol.code}`}
          className="flex items-center gap-2.5 bg-surface border border-border rounded-xl px-3 py-2.5"
        >
          <CompanyLogo code={symbol.code} size={30} />
          <div>
            <div className="font-bold text-sm">${symbol.code}</div>
            <div className="text-xs text-muted">{symbol.name_en}</div>
          </div>
          {quote && (
            <div className="ml-auto text-right">
              <div className="text-sm tnum">{taka(quote.ltp)}</div>
              <div className="text-xs font-semibold">
                <Pct value={quote.change_pct} period="1d" />
              </div>
            </div>
          )}
        </Link>
      ))}
    </div>
  );
}
