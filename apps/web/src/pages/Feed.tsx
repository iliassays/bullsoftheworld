import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useLang } from "../lib/i18n";
import { useInfiniteFeed } from "../lib/useInfiniteFeed";
import { Composer } from "../components/Composer";
import { PostCard } from "../components/PostCard";
import { TickerStrip } from "../components/TickerStrip";
import { TodaysWatch } from "../components/TodaysWatch";
import { WatchlistHome } from "../components/WatchlistHome";
import { Empty, Spinner } from "../components/ui";

export function Feed() {
  const { user } = useAuth();
  const { t } = useLang();
  const { items, setItems, loading, sentinelRef } = useInfiniteFeed(
    "home",
    (l, o) => api.feed(undefined, undefined, l, o),
  );

  return (
    <div className="flex flex-col gap-3">
      <TickerStrip />
      <WatchlistHome />
      <TodaysWatch />
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
