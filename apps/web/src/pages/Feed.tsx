import { Link, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useLang } from "../lib/i18n";
import { useInfiniteFeed } from "../lib/useInfiniteFeed";
import { Composer } from "../components/Composer";
import { DhakaMood } from "../components/DhakaMood";
import { PostCard } from "../components/PostCard";
import { TodaysWatch } from "../components/TodaysWatch";
import { WatchlistHome } from "../components/WatchlistHome";
import { Spinner } from "../components/ui";

// Redesign 2026-07: the Bulls tab lives here now, as a feed filter. Each chip maps straight onto
// the /posts query params the backend already supports — no new endpoint needed.
type Chip = "all" | "desks" | "people" | "myStocks";

export function Feed() {
  const { user } = useAuth();
  const { t } = useLang();
  const [params, setParams] = useSearchParams();
  // /bulls redirects to /?feed=desks so old links (and the FB page) keep working.
  const requested = params.get("feed") as Chip | null;
  const chip: Chip = requested ?? (user ? "all" : "desks");

  const chips: Chip[] = user ? ["all", "desks", "people", "myStocks"] : ["desks", "people"];
  const chipLabel: Record<Chip, string> = {
    all: t("feedchip.all"),
    desks: t("feedchip.desks"),
    people: t("feedchip.people"),
    myStocks: t("feedchip.myStocks"),
  };

  const { items, setItems, loading, sentinelRef } = useInfiniteFeed(
    `home:${!!user}:${chip}`,
    (l, o) => {
      if (chip === "desks") return api.feed(undefined, "note", l, o);
      if (chip === "people") return api.feed(undefined, "user", l, o);
      if (chip === "myStocks") return api.feed(undefined, "user", l, o, undefined, true);
      return user ? api.feed(undefined, undefined, l, o, undefined, true) : Promise.resolve([]);
    },
  );

  const sectionLabel = (text: string) => (
    <div className="text-[11px] font-semibold uppercase tracking-wide text-muted px-1">
      {text}
    </div>
  );

  const pick = (c: Chip) => setParams(c === (user ? "all" : "desks") ? {} : { feed: c });

  return (
    <div className="flex flex-col gap-3">
      {/* Today — one glance: mood, my stocks, what stands out. (Ticker strip and the earnings
          calendar moved out — Markets carries the calendar; see docs/redesign/2026-07-drops.md) */}
      {sectionLabel(t("home.today"))}
      <DhakaMood />
      <WatchlistHome />
      <TodaysWatch />

      {sectionLabel(t("home.myFeed"))}
      <div className="flex gap-2 overflow-x-auto pb-0.5 px-1">
        {chips.map((c) => (
          <button
            key={c}
            onClick={() => pick(c)}
            className={`whitespace-nowrap text-xs font-semibold px-3 py-1.5 rounded-full border ${
              chip === c
                ? "text-accent border-accent bg-accent/10"
                : "text-muted border-border"
            }`}
          >
            {chipLabel[c]}
          </button>
        ))}
      </div>

      {!user && (
        // Logged out: desk notes stay fully browsable; sell the personalized feed alongside.
        <div className="bg-surface border border-border rounded-2xl p-4 text-center">
          <div className="font-bold">{t("home.signedOutTitle")}</div>
          <p className="text-sm text-muted mt-1.5 leading-relaxed">{t("home.signedOutBody")}</p>
          <Link
            to="/me"
            className="inline-block mt-3 rounded-full px-5 py-2 text-sm font-bold bg-accent text-bg hover:opacity-90"
          >
            {t("home.signInCta")}
          </Link>
        </div>
      )}

      {user && chip !== "desks" && (
        <Composer onPosted={(p) => setItems((cur) => [p, ...cur])} />
      )}
      {items.map((p) => (
        <PostCard key={p.id} post={p} />
      ))}
      {loading && <Spinner />}
      {!loading && items.length === 0 && user && (
        // Signed in but nothing followed/watched yet — explain what this feed is + how to fill it.
        <div className="bg-surface border border-border rounded-2xl p-5 text-center">
          <div className="text-2xl">🌱</div>
          <div className="font-bold mt-2">{t("home.emptyTitle")}</div>
          <p className="text-sm text-muted mt-1.5 leading-relaxed">{t("home.emptyBody")}</p>
          <div className="flex gap-2 justify-center mt-3">
            <button
              onClick={() => pick("desks")}
              className="rounded-full px-4 py-2 text-sm font-bold bg-accent text-bg hover:opacity-90"
            >
              {t("home.followDesks")}
            </button>
            <Link
              to="/markets"
              className="rounded-full px-4 py-2 text-sm font-semibold border border-border hover:border-accent hover:text-accent"
            >
              {t("home.watchStocks")}
            </Link>
          </div>
        </div>
      )}
      <div ref={sentinelRef} />
    </div>
  );
}
