import { api } from "../lib/api";
import { useLang } from "../lib/i18n";
import { useInfiniteFeed } from "../lib/useInfiniteFeed";
import { PostCard } from "../components/PostCard";
import { Empty, Spinner } from "../components/ui";

// Bulls Feed — the automated agent desk-notes in full, so they're never washed out by user chatter
// on the home feed. Readable narrative notes (not a screener — the ticker lists live in Markets).
// Repetition is handled by varied wording in the note templates, not by collapsing the text away.
export function BullsFeed() {
  const { t } = useLang();
  const { items, loading, sentinelRef } = useInfiniteFeed("bulls", (l, o) =>
    api.feed(undefined, "note", l, o),
  );

  return (
    <div className="flex flex-col gap-3">
      <div className="bg-surface border border-border rounded-2xl p-4">
        <div className="text-accent font-semibold text-sm">
          🐂 {t("bulls.feedTitle")}
        </div>
        <p className="text-xs text-muted mt-1">{t("bulls.feedDesc")}</p>
      </div>

      {items.map((p) => (
        <PostCard key={p.id} post={p} />
      ))}
      {loading && <Spinner />}
      {!loading && items.length === 0 && <Empty>{t("bulls.empty")}</Empty>}
      <div ref={sentinelRef} />
    </div>
  );
}
