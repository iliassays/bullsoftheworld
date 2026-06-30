import { useEffect, useState } from "react";
import { api, type NoteBeat } from "../lib/api";
import { useLang } from "../lib/i18n";
import { useInfiniteFeed } from "../lib/useInfiniteFeed";
import { PostCard } from "../components/PostCard";
import { Empty, Spinner } from "../components/ui";

// Bulls Feed — the automated agent desk-notes in full, so they're never washed out by user chatter
// on the home feed. Filter chips (Circuit Limit, Accumulation, 52-Week, …) come from the agents that
// actually have notes, so users can jump straight to the category they care about. Descriptive only.
export function BullsFeed() {
  const { t } = useLang();
  const [beats, setBeats] = useState<NoteBeat[]>([]);
  const [active, setActive] = useState<string | null>(null); // null = All

  useEffect(() => {
    api
      .noteBeats()
      .then(setBeats)
      .catch(() => setBeats([]));
  }, []);

  // Re-keying on `active` restarts the feed; the loader reads the current filter.
  const { items, loading, sentinelRef } = useInfiniteFeed(
    `bulls:${active ?? "all"}`,
    (l, o) => api.feed(undefined, "note", l, o, active ?? undefined),
  );

  const chip = (label: string, on: boolean, onClick: () => void) => (
    <button
      onClick={onClick}
      className={`shrink-0 rounded-full border px-3 py-1 text-xs font-semibold transition ${
        on
          ? "text-accent border-accent bg-accent/10"
          : "text-muted border-border hover:text-text"
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="flex flex-col gap-3">
      <div className="bg-surface border border-border rounded-2xl p-4">
        <div className="font-semibold text-sm">🐂 {t("bulls.feedTitle")}</div>
        <p className="text-xs text-muted mt-1">{t("bulls.feedDesc")}</p>
      </div>

      {beats.length > 0 && (
        <div className="flex gap-2 overflow-x-auto -mx-1 px-1 pb-1">
          {chip(t("bulls.all"), active === null, () => setActive(null))}
          {beats.map((b) =>
            chip(b.name, active === b.handle, () => setActive(b.handle)),
          )}
        </div>
      )}

      {items.map((p) => (
        <PostCard key={p.id} post={p} />
      ))}
      {loading && <Spinner />}
      {!loading && items.length === 0 && <Empty>{t("bulls.empty")}</Empty>}
      <div ref={sentinelRef} />
    </div>
  );
}
