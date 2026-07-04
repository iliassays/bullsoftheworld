import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type NoteBeat } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useLang } from "../lib/i18n";
import { useInfiniteFeed } from "../lib/useInfiniteFeed";
import { Composer } from "../components/Composer";
import { DhakaMood } from "../components/DhakaMood";
import { EarningsWeek } from "../components/EarningsWeek";
import { PostCard } from "../components/PostCard";
import { QuizCard } from "../components/QuizCard";
import { TodaysWatch } from "../components/TodaysWatch";
import { Spinner } from "../components/ui";

// Redesign 2026-07: the Bulls tab lives here now, as a feed filter. Each chip maps straight onto
// the /posts query params the backend already supports — no new endpoint needed.
// "myStocks" = watchlist (WatchlistItem) — a stock you're following, not one you own. "portfolio"
// is the distinct, actually-held-shares filter; the chip LABEL says which is which since the two
// are easy to conflate (2026-07-04 user report: the old "My stocks" label read as portfolio).
type Chip = "all" | "desks" | "people" | "myStocks" | "portfolio";

export function Feed() {
  const { user } = useAuth();
  const { t } = useLang();
  const [params, setParams] = useSearchParams();
  // /bulls redirects to /?feed=desks so old links (and the FB page) keep working.
  const requested = params.get("feed") as Chip | null;
  const chip: Chip = requested ?? (user ? "all" : "desks");
  // Which single desk to narrow to within the combined "Desks" stream — restored per user
  // request after the redesign merged per-beat chips into one; a dropdown (not a chip row)
  // avoids the header clutter that merge was meant to fix (docs/redesign/2026-07-drops.md).
  const desk = params.get("desk") || undefined;
  const [beats, setBeats] = useState<NoteBeat[] | null>(null);
  useEffect(() => {
    if (chip !== "desks") return;
    let alive = true;
    api.noteBeats().then((b) => alive && setBeats(b)).catch(() => alive && setBeats([]));
    return () => {
      alive = false;
    };
  }, [chip]);

  const chips: Chip[] = user
    ? ["all", "desks", "people", "myStocks", "portfolio"]
    : ["desks", "people"];
  const chipLabel: Record<Chip, string> = {
    all: t("feedchip.all"),
    desks: t("feedchip.desks"),
    people: t("feedchip.people"),
    myStocks: t("feedchip.myStocks"),
    portfolio: t("feedchip.portfolio"),
  };

  const { items, setItems, loading, sentinelRef } = useInfiniteFeed(
    `home:${!!user}:${chip}:${desk ?? ""}`,
    (l, o) => {
      if (chip === "desks") return api.feed(undefined, "note", l, o, desk);
      if (chip === "people") return api.feed(undefined, "user", l, o);
      if (chip === "myStocks") return api.feed(undefined, "user", l, o, undefined, true);
      if (chip === "portfolio") return api.feed(undefined, "user", l, o, undefined, false, true);
      return user ? api.feed(undefined, undefined, l, o, undefined, true) : Promise.resolve([]);
    },
  );

  const sectionLabel = (text: string) => (
    <div className="text-[11px] font-semibold uppercase tracking-wide text-muted px-1">
      {text}
    </div>
  );

  const pick = (c: Chip) => setParams(c === (user ? "all" : "desks") ? {} : { feed: c });
  const pickDesk = (handle: string) => {
    const next = new URLSearchParams(params);
    if (handle) next.set("desk", handle);
    else next.delete("desk");
    setParams(next);
  };

  return (
    <div className="flex flex-col gap-3">
      {/* Today — one glance: mood, what stands out, today's earnings, a quiz question.
          (Ticker strip dropped and the personalized "Your Watchlist" card removed 2026-07-04 —
          it duplicated /watchlist with a subtly unscoped 'latest note' lookup; the ☆ Watchlist
          feed chip below covers the same job better. See docs/redesign/2026-07-drops.md.) */}
      {sectionLabel(t("home.today"))}
      <DhakaMood />
      <TodaysWatch />
      <EarningsWeek scope="today" />
      <QuizCard />

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

      {chip === "desks" && beats && beats.length > 0 && (
        <select
          value={desk ?? ""}
          onChange={(e) => pickDesk(e.target.value)}
          className="mx-1 rounded-full border border-border bg-card text-xs font-semibold text-fg px-3 py-1.5"
        >
          <option value="">{t("feedchip.allDesks")}</option>
          {beats.map((b) => (
            <option key={b.handle} value={b.handle}>
              {b.name} ({b.count})
            </option>
          ))}
        </select>
      )}

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
