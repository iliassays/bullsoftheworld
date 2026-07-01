import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useLang } from "../lib/i18n";
import { useInfiniteFeed } from "../lib/useInfiniteFeed";
import { Composer } from "../components/Composer";
import { DhakaMood } from "../components/DhakaMood";
import { PostCard } from "../components/PostCard";
import { TickerStrip } from "../components/TickerStrip";
import { TodaysWatch } from "../components/TodaysWatch";
import { WatchlistHome } from "../components/WatchlistHome";
import { Empty, Spinner } from "../components/ui";

export function Feed() {
  const { user } = useAuth();
  const { t } = useLang();
  // Home is the activity stream — human posts + labeled agent notes, newest first — so it stays
  // alive pre-community. 🐂 Bulls is the same auto notes, filterable by category.
  const { items, setItems, loading, sentinelRef } = useInfiniteFeed(
    "home",
    (l, o) => api.feed(undefined, undefined, l, o),
  );

  const sectionLabel = (text: string) => (
    <div className="text-[11px] font-semibold uppercase tracking-wide text-muted px-1">
      {text}
    </div>
  );

  return (
    <div className="flex flex-col gap-3">
      {/* Today — the market-overview dashboard. */}
      {sectionLabel(t("home.today"))}
      <TickerStrip />
      <DhakaMood />
      <WatchlistHome />
      <TodaysWatch />

      {/* Latest — the activity stream: human posts + labeled agent notes. */}
      {sectionLabel(t("home.latest"))}
      {user ? (
        <Composer onPosted={(p) => setItems((cur) => [p, ...cur])} />
      ) : (
        <Link
          to="/me"
          className="block text-center text-sm text-accent bg-surface border border-border rounded-2xl py-3"
        >
          {t("feed.loginCta")}
        </Link>
      )}

      {items.map((p) => (
        <PostCard key={p.id} post={p} />
      ))}
      {loading && <Spinner />}
      {!loading && items.length === 0 && (
        <Empty>{t("feed.empty")}</Empty>
      )}
      <div ref={sentinelRef} />
    </div>
  );
}
