import { useCallback, useEffect, useRef, useState } from "react";
import type { Post } from "./api";

const PAGE = 25;

// Infinite-scroll feed: loads a page at a time, appends as a sentinel scrolls into view.
// `resetKey` re-starts the feed (e.g. when the symbol or tab changes). `load(limit, offset)`
// returns the next page. `setItems` is exposed so callers can prepend (e.g. a new post).
export function useInfiniteFeed(
  resetKey: string,
  load: (limit: number, offset: number) => Promise<Post[]>,
) {
  const [items, setItems] = useState<Post[]>([]);
  const [loading, setLoading] = useState(true);
  const [done, setDone] = useState(false);
  const offset = useRef(0);
  const generation = useRef(0);
  const busyGeneration = useRef<number | null>(null);
  const doneRef = useRef(false);
  const io = useRef<IntersectionObserver | null>(null);
  const loadRef = useRef(load);
  loadRef.current = load;

  const more = useCallback(async () => {
    const requestGeneration = generation.current;
    if (busyGeneration.current === requestGeneration || doneRef.current) return;
    busyGeneration.current = requestGeneration;
    setLoading(true);
    try {
      const batch = await loadRef.current(PAGE, offset.current);
      // A filter/tab change can finish while the previous request is still in flight. Ignore that
      // stale response so it cannot leak posts into the newly reset feed.
      if (requestGeneration !== generation.current) return;
      offset.current += batch.length;
      setItems((current) => {
        const seen = new Set(current.map((post) => post.id));
        const unique = batch.filter((post) => {
          if (seen.has(post.id)) return false;
          seen.add(post.id);
          return true;
        });
        return [...current, ...unique];
      });
      if (batch.length < PAGE) {
        doneRef.current = true;
        setDone(true);
      }
    } catch {
      doneRef.current = true;
      setDone(true);
    } finally {
      if (busyGeneration.current === requestGeneration) busyGeneration.current = null;
      if (requestGeneration === generation.current) setLoading(false);
    }
  }, []);

  // (re)start whenever the key changes
  useEffect(() => {
    generation.current += 1;
    offset.current = 0;
    busyGeneration.current = null;
    doneRef.current = false;
    setItems([]);
    setDone(false);
    more();
  }, [resetKey, more]);

  // Callback ref: (re)attach the observer whenever the sentinel mounts — robust to the node
  // appearing/disappearing as tabs switch.
  const sentinelRef = useCallback(
    (node: HTMLDivElement | null) => {
      io.current?.disconnect();
      if (node) {
        io.current = new IntersectionObserver(
          (entries) => {
            if (entries[0].isIntersecting) more();
          },
          { rootMargin: "300px" },
        );
        io.current.observe(node);
      }
    },
    [more],
  );

  return { items, setItems, loading, done, sentinelRef };
}
