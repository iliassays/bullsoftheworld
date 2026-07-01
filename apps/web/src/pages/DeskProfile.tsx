import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, type Desk } from "../lib/api";
import { useLang } from "../lib/i18n";
import { useInfiniteFeed } from "../lib/useInfiniteFeed";
import { PostCard } from "../components/PostCard";
import { Avatar, Empty, Spinner, VerifiedBadge } from "../components/ui";

// Official desk profile — StockTwits-style: header (name + verified badge + official label + bio +
// joined + post count) then all of the desk's posts. Follow arrives in Phase 3.
export function DeskProfile() {
  const { handle = "" } = useParams();
  const { t } = useLang();
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

  const { items, loading, sentinelRef } = useInfiniteFeed(`desk:${handle}`, (l, o) =>
    api.feed(undefined, "note", l, o, handle),
  );

  if (failed) return <Empty>{t("desk.notFound")}</Empty>;
  if (!desk) return <Spinner />;

  return (
    <div className="flex flex-col gap-3">
      <div className="bg-surface border border-border rounded-2xl p-4">
        <div className="flex items-start gap-3">
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

        <p className="text-sm text-text/90 leading-relaxed mt-3">{desk.bio}</p>

        <div className="flex gap-4 mt-3 text-xs text-muted">
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
