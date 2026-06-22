import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Post } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Composer } from "../components/Composer";
import { PostCard } from "../components/PostCard";
import { TickerStrip } from "../components/TickerStrip";
import { Empty, Spinner } from "../components/ui";

export function Feed() {
  const { user } = useAuth();
  const [posts, setPosts] = useState<Post[] | null>(null);

  useEffect(() => {
    api.feed().then(setPosts).catch(() => setPosts([]));
  }, []);

  return (
    <div className="flex flex-col gap-3">
      <TickerStrip />
      {user ? (
        <Composer onPosted={(p) => setPosts((cur) => [p, ...(cur ?? [])])} />
      ) : (
        <Link
          to="/me"
          className="block text-center text-sm text-accent bg-surface border border-border rounded-2xl py-3"
        >
          Log in to post your call →
        </Link>
      )}

      {posts === null ? (
        <Spinner />
      ) : posts.length === 0 ? (
        <Empty>No posts yet. Be the first to call $GP.</Empty>
      ) : (
        posts.map((p) => <PostCard key={p.id} post={p} />)
      )}
    </div>
  );
}
