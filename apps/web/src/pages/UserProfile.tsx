import { useEffect, useState } from "react";
import { useSeo } from "../components/Seo";
import { useParams } from "react-router-dom";
import { Link } from "../lib/nav";
import { api, type PublicPortfolio, type UserProfile as UserProfileT } from "../lib/api";
import { useLang } from "../lib/i18n";
import { useInfiniteFeed } from "../lib/useInfiniteFeed";
import { CompanyLogo } from "../components/CompanyLogo";
import { PortfolioGrowthChart } from "../components/PortfolioGrowthChart";
import { PostCard } from "../components/PostCard";
import { Empty, Pct, Spinner, taka } from "../components/ui";

// A regular member's public profile — StockTwits-style header (avatar, joined, post count) +
// their posts, same shape as DeskProfile but without the official/follow trappings (those are
// desk-only). Portfolio only renders if the member has explicitly opted in (portfolio_public);
// the backend already refuses to serve it otherwise, so a missing section here is normal, not
// an error — see PATCH /portfolio/visibility.
export function UserProfile() {
  const { handle = "" } = useParams();
  const { t } = useLang();
  useSeo({ noindex: true }); // private/personal — keep out of the index
  const [profile, setProfile] = useState<UserProfileT | null>(null);
  const [failed, setFailed] = useState(false);
  const [pf, setPf] = useState<PublicPortfolio | null>(null);

  useEffect(() => {
    setProfile(null);
    setFailed(false);
    setPf(null);
    api
      .userProfile(handle)
      .then((p) => {
        setProfile(p);
        if (p.portfolio_public) api.userPortfolio(handle).then(setPf).catch(() => {});
      })
      .catch(() => setFailed(true));
  }, [handle]);

  const { items, loading, sentinelRef } = useInfiniteFeed(`user:${handle}`, (l, o) =>
    api.feed(undefined, "user", l, o, handle),
  );

  if (failed) return <Empty>{t("userProfile.notFound")}</Empty>;
  if (!profile) return <Spinner />;

  const initials = profile.name
    .split(/\s+/)
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className="flex flex-col gap-3">
      <div className="bg-card rounded-2xl overflow-hidden">
        <div className="h-1.5 bg-border" />
        <div className="p-5">
          <div className="flex items-start gap-4 min-w-0">
            <div className="w-16 h-16 shrink-0 rounded-full grid place-items-center bg-surface border-2 border-border text-accent font-extrabold text-xl">
              {initials}
            </div>
            <div className="min-w-0">
              <div className="text-xl font-extrabold leading-tight">{profile.name}</div>
              <div className="text-xs text-muted">@{profile.handle}</div>
            </div>
          </div>
          <div className="flex gap-4 mt-3 text-xs text-muted">
            <span>
              <b className="text-text">{profile.posts.toLocaleString()}</b>{" "}
              {t("desk.posts")}
            </span>
            <span>
              {t("desk.joined")} {profile.joined}
            </span>
          </div>
        </div>
      </div>

      {/* Portfolio — only when the member has opted in. Read-only: no alert/edit affordances,
          those are private to the owner's own /portfolio view. */}
      {profile.portfolio_public && pf && pf.holdings.length > 0 && (
        <>
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted px-1 pt-1">
            {t("userProfile.portfolioHeading")}
          </div>
          <div className="bg-surface border border-border rounded-2xl p-4 text-center">
            <div className="text-[11px] text-muted uppercase tracking-wide">
              {t("pf.totalValue")}
            </div>
            <div className="text-2xl font-bold tnum mt-1">
              {pf.total_value != null ? taka(pf.total_value) : "—"}
            </div>
            {pf.total_pnl_pct != null && (
              <div className="text-sm font-semibold mt-1">
                <Pct value={pf.total_pnl_pct} /> <span className="text-muted font-normal">{t("pf.allTime")}</span>
              </div>
            )}
          </div>

          <PortfolioGrowthChart handle={handle} />

          <div className="bg-surface border border-border rounded-2xl p-3">
            {pf.holdings.map((h) => (
              <Link
                key={h.code}
                to={`/s/${h.code}`}
                className="flex items-center gap-2.5 py-2.5 border-t border-border first:border-t-0"
              >
                <CompanyLogo code={h.code} size={30} />
                <div className="min-w-0">
                  <div className="text-sm font-bold">${h.code}</div>
                  <div className="text-[11px] text-muted tnum">
                    {h.quantity.toLocaleString()} × {taka(h.avg_cost)}
                  </div>
                </div>
                <div className="ml-auto text-right tnum">
                  <div className="text-sm font-semibold">
                    {h.value != null ? taka(h.value) : "—"}
                  </div>
                  {h.pnl_pct != null && (
                    <div className="text-xs font-semibold">
                      <Pct value={h.pnl_pct} period="sinceBuy" />
                    </div>
                  )}
                </div>
              </Link>
            ))}
          </div>
        </>
      )}

      <div className="text-[11px] font-semibold uppercase tracking-wide text-muted px-1 pt-1">
        {t("desk.postsHeading")}
      </div>

      {items.map((p) => (
        <PostCard key={p.id} post={p} />
      ))}
      {loading && <Spinner />}
      {!loading && items.length === 0 && <Empty>{t("desk.noPosts")}</Empty>}
      <div ref={sentinelRef} />
    </div>
  );
}
