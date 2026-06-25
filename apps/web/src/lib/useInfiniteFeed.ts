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
  const busy = useRef(false);
  const doneRef = useRef(false);
  const io = useRef<IntersectionObserver | null>(null);
  const loadRef = useRef(load);
  loadRef.current = load;

  const more = useCallback(async () => {
    if (busy.current || doneRef.current) return;
    busy.current = true;
    setLoading(true);
    try {
      const batch = await loadRef.current(PAGE, offset.current);
      offset.current += batch.length;
      setItems((cur) => [...cur, ...batch]);
      if (batch.length < PAGE) {
        doneRef.current = true;
        setDone(true);
      }
    } catch {
      doneRef.current = true;
      setDone(true);
    } finally {
      busy.current = false;
      setLoading(false);
    }
  }, []);

  // (re)start whenever the key changes
  useEffect(() => {
    offset.current = 0;
    busy.current = false;
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
