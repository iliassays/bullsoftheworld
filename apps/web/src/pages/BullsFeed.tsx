import { useEffect, useState } from "react";
import { api, type Post } from "../lib/api";
import { PostCard } from "../components/PostCard";
import { Empty, Spinner } from "../components/ui";

// Bulls Feed — only the automated agent desk-notes, so they're never lost under chatter.
export function BullsFeed() {
  const [notes, setNotes] = useState<Post[] | null>(null);

  useEffect(() => {
    api
      .feed(undefined, "note")
      .then(setNotes)
      .catch(() => setNotes([]));
  }, []);

  return (
    <div className="flex flex-col gap-3">
      <div className="bg-surface border border-border rounded-2xl p-4">
        <div className="text-accent font-semibold text-sm">🐂 Bulls Feed</div>
        <p className="text-xs text-muted mt-1">
          Automated data notes across the market — levels, volume, ownership and
          more. Descriptive, not advice.
        </p>
      </div>

      {notes === null ? (
        <Spinner />
      ) : notes.length === 0 ? (
        <Empty>No notes yet — they appear as the market moves.</Empty>
      ) : (
        notes.map((p) => <PostCard key={p.id} post={p} />)
      )}
    </div>
  );
}
