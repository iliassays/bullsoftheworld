import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type Desk } from "../lib/api";
import { deskIcon } from "../lib/deskIcons";
import { useAuth } from "../lib/auth";
import { useLang } from "../lib/i18n";
import { useInfiniteFeed } from "../lib/useInfiniteFeed";
import { PostCard } from "../components/PostCard";
import { Empty, Spinner, VerifiedBadge } from "../components/ui";

// Official desk profile — StockTwits-style: header (name + verified badge + official label + bio +
// joined + post count) then all of the desk's posts. Follow arrives in Phase 3.
export function DeskProfile() {
  const { handle = "" } = useParams();
  const { t } = useLang();
  const { user } = useAuth();
  const [desk, setDesk] = useState<Desk | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setDesk(null);
    setFailed(false);
    api
      .desk(handle)
      .then(setDesk)
      .catch(() => setFailed(true));
  }, [handle]);

  const toggleFollow = async () => {
    if (!desk) return;
    const next = !desk.following;
    // optimistic
    setDesk({
      ...desk,
      following: next,
      followers: desk.followers + (next ? 1 : -1),
    });
    try {
      if (next) await api.followDesk(handle);
      else await api.unfollowDesk(handle);
    } catch {
      setDesk((d) =>
        d ? { ...d, following: !next, followers: d.followers + (next ? -1 : 1) } : d,
      );
    }
  };

  const { items, loading, sentinelRef } = useInfiniteFeed(`desk:${handle}`, (l, o) =>
    api.feed(undefined, "note", l, o, handle),
  );

  if (failed) return <Empty>{t("desk.notFound")}</Empty>;
  if (!desk) return <Spinner />;

  const icon = deskIcon(desk.handle);
  const initials = desk.name
    .split(/\s+/)
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className="flex flex-col gap-3">
      {/* Profile header — deliberately distinct from the post cards: gold top rule, lighter surface,
          a big ringed avatar and a large name, so it reads as a header, not another note. */}
      <div className="bg-card rounded-2xl overflow-hidden">
        <div className="h-1.5 bg-accent" />
        <div className="p-5">
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-start gap-4 min-w-0">
              <div className="w-16 h-16 shrink-0 rounded-full grid place-items-center bg-surface border-2 border-accent/60 text-accent font-extrabold text-xl">
                {icon ? <span className="text-3xl leading-none">{icon}</span> : initials}
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-1.5 text-xl font-extrabold leading-tight">
                  {desk.name}
                  <VerifiedBadge size={18} />
                </div>
                <div className="text-xs text-muted">@{desk.handle}</div>
                <span className="inline-block mt-1.5 text-[11px] font-semibold text-accent bg-accent/10 border border-accent/30 rounded-full px-2 py-0.5">
                  🏛️ {t("desk.official")}
                </span>
              </div>
            </div>
            {user ? (
              <button
                onClick={toggleFollow}
                className={`shrink-0 rounded-full px-5 py-2 text-sm font-bold transition ${
                  desk.following
                    ? "bg-accent/10 text-accent border border-accent"
                    : "bg-accent text-bg hover:opacity-90"
                }`}
              >
                {desk.following ? `✓ ${t("desk.following")}` : t("desk.follow")}
              </button>
            ) : (
              <Link
                to="/me"
                className="shrink-0 rounded-full px-5 py-2 text-sm font-bold bg-accent text-bg hover:opacity-90"
              >
                {t("desk.follow")}
              </Link>
            )}
          </div>

          <p className="text-sm text-text/90 leading-relaxed mt-4">{desk.bio}</p>

          <div className="flex gap-4 mt-3 text-xs text-muted">
            <span>
              <b className="text-text">{desk.followers.toLocaleString()}</b>{" "}
              {t("desk.followers")}
            </span>
            <span>
              <b className="text-text">{desk.posts.toLocaleString()}</b> {t("desk.posts")}
            </span>
            <span>
              {t("desk.joined")} {desk.joined}
            </span>
          </div>
        </div>
      </div>

      {/* Divider so the header clearly ends and the post stream begins. */}
      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted px-1 pt-1">
        {t("desk.postsHeading")}
      </div>

      {items.map((p) => (
        <PostCard key={p.id} post={p} />
      ))}
      {loading && <Spinner />}
      {!loading && items.length === 0 && <Empty>{t("desk.noPosts")}</Empty>}
      <div ref={sentinelRef} />
    </div>
  );
}
