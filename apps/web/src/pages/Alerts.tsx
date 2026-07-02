import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type AlertItem } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useLang } from "../lib/i18n";
import { formatDhakaDateTime } from "../lib/time";
import { Empty, Spinner } from "../components/ui";

// Icon per alert kind — visual state first, text second, so the inbox scans at a glance.
const KIND_ICON: Record<string, string> = {
  price_cross: "🎯",
  signal: "📈",
  ownership: "🏛️",
  earnings: "🗓️",
};

export function Alerts() {
  const { user } = useAuth();
  const { t } = useLang();
  const [items, setItems] = useState<AlertItem[] | null>(null);

  useEffect(() => {
    if (!user) return;
    api
      .alerts()
      .then((list) => {
        setItems(list);
        // Opening the inbox clears the bell badge; individual cards keep their unread tint
        // until the next visit so "what's new" is still visible this once.
        if (list.some((a) => !a.read)) api.alertsMarkRead().catch(() => {});
      })
      .catch(() => setItems([]));
  }, [user]);

  if (!user)
    return (
      <div className="bg-surface border border-border rounded-2xl p-5 text-center">
        <div className="text-3xl">🔔</div>
        <div className="font-bold mt-2">{t("alerts.loginTitle")}</div>
        <p className="text-sm text-muted mt-1.5">{t("alerts.loginBody")}</p>
        <Link
          to="/me"
          className="inline-block mt-3 rounded-full px-5 py-2 text-sm font-bold bg-accent text-bg hover:opacity-90"
        >
          {t("home.signInCta")}
        </Link>
      </div>
    );

  return (
    <div className="flex flex-col gap-3">
      <div className="px-1">
        <h1 className="font-bold text-lg">🔔 {t("alerts.title")}</h1>
        <p className="text-xs text-muted">{t("alerts.subtitle")}</p>
      </div>
      {items === null && <Spinner />}
      {items !== null && items.length === 0 && <Empty>{t("alerts.empty")}</Empty>}
      {items?.map((a) => (
        <Link
          key={a.id}
          to={a.code ? `/s/${a.code}` : "/"}
          className={`block bg-surface border rounded-2xl p-3.5 transition hover:border-accent ${
            a.read ? "border-border" : "border-accent/50 bg-accent/5"
          }`}
        >
          <div className="flex gap-2.5">
            <span className="text-xl leading-none pt-0.5" aria-hidden>
              {KIND_ICON[a.kind] ?? "🔔"}
            </span>
            <div className="min-w-0">
              <div className="text-sm font-semibold leading-snug">{a.title}</div>
              {a.body && (
                <div className="text-xs text-muted mt-1 leading-relaxed">{a.body}</div>
              )}
              <div className="text-[10px] text-muted mt-1.5 tnum">
                {formatDhakaDateTime(a.created_at)}
              </div>
            </div>
          </div>
        </Link>
      ))}
    </div>
  );
}
