import { useState } from "react";
import { Link } from "react-router-dom";
import { api, type Post, type ReactionKind } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useLang } from "../lib/i18n";
import { Composer } from "./Composer";
import { Avatar, SentimentTag, VerifiedBadge } from "./ui";

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
          <Link
            key={i}
            to={`/s/${p.slice(1).toUpperCase()}`}
            className="text-accent font-semibold"
          >
            {p.toUpperCase()}
          </Link>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </p>
  );
}

// isReply renders a lighter card without its own reply thread (no nested threads in Phase A).
export function PostCard({
  post,
  isReply = false,
}: {
  post: Post;
  isReply?: boolean;
}) {
  const { user } = useAuth();
  const { t } = useLang();

  // conviction state (optimistic)
  const [agree, setAgree] = useState(post.agree);
  const [disagree, setDisagree] = useState(post.disagree);
  const [mine, setMine] = useState<ReactionKind | null>(post.my_reaction);

  // replies
  const [open, setOpen] = useState(false);
  const [replies, setReplies] = useState<Post[] | null>(null);
  const [replyCount, setReplyCount] = useState(post.reply_count);

  const react = async (kind: ReactionKind) => {
    if (!user) return;
    const prev = { agree, disagree, mine };
    let na = agree;
    let nd = disagree;
    if (mine === "agree") na--;
    if (mine === "disagree") nd--;
    const next: ReactionKind | null = mine === kind ? null : kind;
    if (next === "agree") na++;
    if (next === "disagree") nd++;
    setAgree(na);
    setDisagree(nd);
    setMine(next);
    try {
      if (next === null) await api.unreact(post.id);
      else await api.react(post.id, next);
    } catch {
      setAgree(prev.agree);
      setDisagree(prev.disagree);
      setMine(prev.mine);
    }
  };

  const toggleThread = async () => {
    const next = !open;
    setOpen(next);
    if (next && replies === null) {
      try {
        setReplies(await api.replies(post.id));
      } catch {
        setReplies([]);
      }
    }
  };

  const onReplied = (p: Post) => {
    setReplies((r) => [...(r ?? []), p]);
    setReplyCount((c) => c + 1);
  };

  const isNote = post.kind === "note";

  const pill = (active: boolean) =>
    `text-xs font-semibold px-2.5 py-1 rounded-full border transition ${
      active
        ? "text-accent border-accent bg-accent/10"
        : "text-muted border-border hover:text-text"
    }`;
  // read-only tally shown to logged-out visitors (no button affordance)
  const readonlyPill =
    "text-xs font-semibold px-2.5 py-1 rounded-full border border-border text-muted";

  return (
    <article
      className={`rounded-2xl border bg-surface border-border ${isReply ? "p-3" : "p-4"}`}
    >
      <header className="flex items-center gap-2.5">
        <Avatar name={post.author.name} />
        <div className="leading-tight">
          <b className="text-sm">
            {post.author.name}
            {isNote && (
              <>
                {" "}
                <VerifiedBadge />
              </>
            )}
          </b>
          <span className="block text-xs text-muted">
            {isNote ? (
              <span className="text-muted">🏛️ {t("post.officialDesk")}</span>
            ) : (
              `@${post.author.handle}`
            )}{" "}
            · {ago(post.created_at)}
          </span>
        </div>
        <div className="ml-auto">
          <SentimentTag s={post.sentiment} />
        </div>
      </header>
      <Body text={post.body} />
      {post.image_url && (
        <img
          src={post.image_url}
          alt=""
          loading="lazy"
          className="w-full rounded-xl border border-border my-2"
        />
      )}
      {post.cashtags.length > 0 && (
        <div className="flex gap-1.5 flex-wrap">
          {post.cashtags.map((c) => {
            const chg = post.cashtag_changes?.[c];
            return (
              <Link
                key={c}
                to={`/s/${c}`}
                className="text-xs bg-card border border-border rounded-full px-2.5 py-1"
              >
                ${c}
                {chg != null && (
                  <span
                    className={`tnum ml-1 ${chg >= 0 ? "text-up" : "text-down"}`}
                  >
                    {chg >= 0 ? "+" : ""}
                    {chg.toFixed(1)}%
                  </span>
                )}
              </Link>
            );
          })}
        </div>
      )}

      {/* conviction + replies */}
      <div className="flex items-center gap-2 mt-3">
        {user ? (
          <>
            <button
              onClick={() => react("agree")}
              className={pill(mine === "agree")}
              title={t("post.agree")}
            >
              👍 {t("post.agreeBtn")}
              {agree > 0 ? ` ${agree}` : ""}
            </button>
            <button
              onClick={() => react("disagree")}
              className={pill(mine === "disagree")}
              title={t("post.disagree")}
            >
              👎 {t("post.disagreeBtn")}
              {disagree > 0 ? ` ${disagree}` : ""}
            </button>
          </>
        ) : (
          // Logged-out: counts are read-only info; tapping invites login rather than dead-ending.
          <Link
            to="/me"
            title={t("post.loginReact")}
            className="flex items-center gap-2"
          >
            <span className={readonlyPill}>👍 {agree}</span>
            <span className={readonlyPill}>👎 {disagree}</span>
          </Link>
        )}
        {(replyCount > 0 || !!user) && !isReply && (
          <button
            onClick={toggleThread}
            className="text-xs text-muted hover:text-text ml-auto"
          >
            💬{" "}
            {replyCount > 0
              ? `${replyCount} ${replyCount === 1 ? t("post.reply") : t("post.replies")}`
              : t("common.reply")}
          </button>
        )}
      </div>

      {open && !isReply && (
        <div className="mt-3 border-t border-border pt-3 flex flex-col gap-2">
          {user ? (
            <Composer
              parentId={post.id}
              compact
              placeholder={t("post.replyPlaceholder")}
              onPosted={onReplied}
            />
          ) : (
            <Link to="/me" className="text-xs text-accent">
              {t("post.loginReply")}
            </Link>
          )}
          {replies === null ? (
            <p className="text-muted text-xs">{t("common.loading")}</p>
          ) : replies.length === 0 ? (
            <p className="text-muted text-xs">{t("post.noReplies")}</p>
          ) : (
            replies.map((r) => <PostCard key={r.id} post={r} isReply />)
          )}
        </div>
      )}
    </article>
  );
}
