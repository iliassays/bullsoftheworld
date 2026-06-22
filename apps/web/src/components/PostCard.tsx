import { Link } from "react-router-dom";
import type { Post } from "../lib/api";
import { Avatar, SentimentTag } from "./ui";

const ago = (iso: string) => {
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
};

// Render body with $CASHTAGS linked to their symbol page.
function Body({ text }: { text: string }) {
  const parts = text.split(/(\$[A-Za-z0-9]{2,16})/g);
  return (
    <p className="text-[15px] leading-relaxed text-text/90 my-2 break-words">
      {parts.map((p, i) =>
        /^\$[A-Za-z0-9]{2,16}$/.test(p) ? (
          <Link key={i} to={`/s/${p.slice(1).toUpperCase()}`} className="text-accent font-semibold">
            {p.toUpperCase()}
          </Link>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </p>
  );
}

export function PostCard({ post }: { post: Post }) {
  return (
    <article className="bg-surface border border-border rounded-2xl p-4">
      <header className="flex items-center gap-2.5">
        <Avatar name={post.author.name} />
        <div className="leading-tight">
          <b className="text-sm">{post.author.name}</b>
          <span className="block text-xs text-muted">
            @{post.author.handle} · {ago(post.created_at)}
          </span>
        </div>
        <div className="ml-auto">
          <SentimentTag s={post.sentiment} />
        </div>
      </header>
      <Body text={post.body} />
      {post.cashtags.length > 0 && (
        <div className="flex gap-1.5 flex-wrap">
          {post.cashtags.map((c) => (
            <Link
              key={c}
              to={`/s/${c}`}
              className="text-xs text-accent bg-accent/10 px-2 py-0.5 rounded-full"
            >
              ${c}
            </Link>
          ))}
        </div>
      )}
    </article>
  );
}
