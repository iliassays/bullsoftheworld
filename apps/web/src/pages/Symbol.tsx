import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, type Post, type SymbolDetail } from "../lib/api";
import { useAuth } from "../lib/auth";
import { CandleChart } from "../components/CandleChart";
import { Composer } from "../components/Composer";
import { DigestPanel } from "../components/DigestPanel";
import { PostCard } from "../components/PostCard";
import { Technicals } from "../components/Technicals";
import { Empty, Pct, Spinner, taka } from "../components/ui";

export function SymbolPage() {
  const { code = "" } = useParams();
  const sym = code.toUpperCase();
  const { user } = useAuth();
  const [detail, setDetail] = useState<SymbolDetail | null>(null);
  const [posts, setPosts] = useState<Post[] | null>(null);
  const [watched, setWatched] = useState(false);

  useEffect(() => {
    setDetail(null);
    setPosts(null);
    api.symbol(sym).then(setDetail).catch(() => setDetail(null));
    api.feed(sym).then(setPosts).catch(() => setPosts([]));
    if (user) api.watchlist().then((w) => setWatched(w.some((i) => i.symbol.code === sym)));
  }, [sym, user]);

  const toggleWatch = async () => {
    if (watched) await api.watchRemove(sym);
    else await api.watchAdd(sym);
    setWatched(!watched);
  };

  if (detail === null) return <Spinner />;
  const q = detail.quote;

  return (
    <div className="flex flex-col gap-3">
      <div className="bg-surface border border-border rounded-2xl p-4">
        <div className="flex items-start">
          <div>
            <div className="text-xl font-bold text-accent">${sym}</div>
            <div className="text-xs text-muted">{detail.symbol.name_en}</div>
          </div>
          {user && (
            <button
              onClick={toggleWatch}
              className={`ml-auto text-sm px-3 py-1.5 rounded-full border ${
                watched ? "text-accent border-accent bg-accent/10" : "text-muted border-border"
              }`}
            >
              {watched ? "★ Watching" : "☆ Watch"}
            </button>
          )}
        </div>
        {q ? (
          <div className="mt-3 flex items-end gap-3">
            <div className="text-2xl font-bold tnum">{taka(q.ltp)}</div>
            <div className="text-sm font-semibold pb-1">
              <Pct value={q.change_pct} />
            </div>
            <div className="ml-auto text-right text-xs text-muted tnum">
              <div>H {q.high} · L {q.low}</div>
              <div>Vol {q.volume.toLocaleString()}</div>
            </div>
          </div>
        ) : (
          <div className="text-muted text-sm mt-2">No quote yet.</div>
        )}
        <div className="text-[10px] text-muted mt-2">⏱ delayed · as of {new Date(q?.as_of ?? "").toLocaleString()}</div>
      </div>

      <DigestPanel code={sym} />

      <CandleChart code={sym} />

      <Technicals code={sym} />

      {user && <Composer initial={`$${sym} `} onPosted={(p) => setPosts((c) => [p, ...(c ?? [])])} />}

      {posts === null ? (
        <Spinner />
      ) : posts.length === 0 ? (
        <Empty>No posts about ${sym} yet.</Empty>
      ) : (
        posts.map((p) => <PostCard key={p.id} post={p} />)
      )}
    </div>
  );
}
