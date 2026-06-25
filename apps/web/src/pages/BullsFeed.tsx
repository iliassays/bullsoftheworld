import { api } from "../lib/api";
import { useInfiniteFeed } from "../lib/useInfiniteFeed";
import { PostCard } from "../components/PostCard";
import { Empty, Spinner } from "../components/ui";

// Bulls Feed — only the automated agent desk-notes, so they're never lost under chatter.
export function BullsFeed() {
  const { items, loading, sentinelRef } = useInfiniteFeed("bulls", (l, o) =>
    api.feed(undefined, "note", l, o),
  );

  return (
    <div className="flex flex-col gap-3">
      <div className="bg-surface border border-border rounded-2xl p-4">
        <div className="text-accent font-semibold text-sm">🐂 Bulls Feed</div>
        <p className="text-xs text-muted mt-1">
          Automated data notes across the market — levels, volume, ownership and
          more. Descriptive, not advice.
        </p>
      </div>

      {items.map((p) => (
        <PostCard key={p.id} post={p} />
      ))}
      {loading && <Spinner />}
      {!loading && items.length === 0 && (
        <Empty>No notes yet — they appear as the market moves.</Empty>
      )}
      <div ref={sentinelRef} />
    </div>
  );
}
