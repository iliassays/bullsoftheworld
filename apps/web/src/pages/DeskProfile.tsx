import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type Desk } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useLang } from "../lib/i18n";
import { useInfiniteFeed } from "../lib/useInfiniteFeed";
import { PostCard } from "../components/PostCard";
import { Avatar, Empty, Spinner, VerifiedBadge } from "../components/ui";

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

  return (
    <div className="flex flex-col gap-3">
      <div className="bg-surface border border-border rounded-2xl p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 min-w-0">
            <Avatar name={desk.name} />
            <div className="min-w-0">
              <div className="flex items-center gap-1.5 font-extrabold text-lg leading-tight">
                {desk.name}
                <VerifiedBadge size={17} />
              </div>
              <span className="inline-block mt-1 text-[11px] font-semibold text-accent bg-accent/10 border border-accent/30 rounded-full px-2 py-0.5">
                🏛️ {t("desk.official")}
              </span>
            </div>
          </div>
          {user ? (
            <button
              onClick={toggleFollow}
              className={`shrink-0 rounded-full px-4 py-1.5 text-sm font-bold transition ${
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
              className="shrink-0 rounded-full px-4 py-1.5 text-sm font-bold bg-accent text-bg hover:opacity-90"
            >
              {t("desk.follow")}
            </Link>
          )}
        </div>

        <p className="text-sm text-text/90 leading-relaxed mt-3">{desk.bio}</p>

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

      {items.map((p) => (
        <PostCard key={p.id} post={p} />
      ))}
      {loading && <Spinner />}
      {!loading && items.length === 0 && <Empty>{t("desk.noPosts")}</Empty>}
      <div ref={sentinelRef} />
    </div>
  );
}
