import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useLang } from "../lib/i18n";
import { useInfiniteFeed } from "../lib/useInfiniteFeed";
import { Composer } from "../components/Composer";
import { DhakaMood } from "../components/DhakaMood";
import { EarningsWeek } from "../components/EarningsWeek";
import { PostCard } from "../components/PostCard";
import { TickerStrip } from "../components/TickerStrip";
import { TodaysWatch } from "../components/TodaysWatch";
import { WatchlistHome } from "../components/WatchlistHome";
import { Spinner } from "../components/ui";

export function Feed() {
  const { user } = useAuth();
  const { t } = useLang();
  // Home is your personal feed: posts from the desks you follow + the companies you watch. Only
  // fetched when signed in; logged-out gets a sign-in pitch instead. 🐂 Bulls stays public + full.
  const { items, setItems, loading, sentinelRef } = useInfiniteFeed(
    `home:${!!user}`,
    (l, o) =>
      user ? api.feed(undefined, undefined, l, o, undefined, true) : Promise.resolve([]),
  );

  const sectionLabel = (text: string) => (
    <div className="text-[11px] font-semibold uppercase tracking-wide text-muted px-1">
      {text}
    </div>
  );

  return (
    <div className="flex flex-col gap-3">
      {/* Today — the market-overview dashboard (shown to everyone). */}
      {sectionLabel(t("home.today"))}
      <TickerStrip />
      <DhakaMood />
      <WatchlistHome />
      <TodaysWatch />
      <EarningsWeek />

      {sectionLabel(t("home.myFeed"))}
      {!user ? (
        // Logged out: sell the personalized feed. Everything is still browsable in 🐂 Bulls.
        <div className="bg-surface border border-border rounded-2xl p-5 text-center">
          <div className="text-3xl">📈</div>
          <div className="font-bold mt-2">{t("home.signedOutTitle")}</div>
          <p className="text-sm text-muted mt-1.5 leading-relaxed">
            {t("home.signedOutBody")}
          </p>
          <Link
            to="/me"
            className="inline-block mt-3 rounded-full px-5 py-2 text-sm font-bold bg-accent text-bg hover:opacity-90"
          >
            {t("home.signInCta")}
          </Link>
          <Link to="/bulls" className="block text-xs text-muted mt-3 hover:text-text">
            {t("home.browseBulls")}
          </Link>
        </div>
      ) : (
        <>
          <Composer onPosted={(p) => setItems((cur) => [p, ...cur])} />
          {items.map((p) => (
            <PostCard key={p.id} post={p} />
          ))}
          {loading && <Spinner />}
          {!loading && items.length === 0 && (
            // Signed in but nothing followed/watched yet — explain what this feed is + how to fill it.
            <div className="bg-surface border border-border rounded-2xl p-5 text-center">
              <div className="text-2xl">🌱</div>
              <div className="font-bold mt-2">{t("home.emptyTitle")}</div>
              <p className="text-sm text-muted mt-1.5 leading-relaxed">
                {t("home.emptyBody")}
              </p>
              <div className="flex gap-2 justify-center mt-3">
                <Link
                  to="/bulls"
                  className="rounded-full px-4 py-2 text-sm font-bold bg-accent text-bg hover:opacity-90"
                >
                  {t("home.followDesks")}
                </Link>
                <Link
                  to="/markets"
                  className="rounded-full px-4 py-2 text-sm font-semibold border border-border hover:border-accent hover:text-accent"
                >
                  {t("home.watchStocks")}
                </Link>
              </div>
            </div>
          )}
        </>
      )}
      <div ref={sentinelRef} />
    </div>
  );
}
