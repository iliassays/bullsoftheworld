import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  api,
  type Buzz,
  type Company,
  type NewsItem,
  type Post,
  type SymbolDetail,
} from "../lib/api";
import { useAuth } from "../lib/auth";
import { useInfiniteFeed } from "../lib/useInfiniteFeed";
import { CandleChart } from "../components/CandleChart";
import { Composer } from "../components/Composer";
import {
  EarningsPanel,
  FundamentalsPanel,
  NewsPanel,
  OwnershipPanel,
} from "../components/CompanyPanels";
import { BeforeYouTrade } from "../components/BeforeYouTrade";
import { DigestPanel } from "../components/DigestPanel";
import { KeyLevels } from "../components/KeyLevels";
import { PlainReadCard } from "../components/PlainReadCard";
import { PulseGauges } from "../components/PulseGauges";
import { PostCard } from "../components/PostCard";
import { Technicals } from "../components/Technicals";
import { Empty, Pct, Spinner, taka } from "../components/ui";

type Tab =
  | "overview"
  | "feed"
  | "bulls"
  | "news"
  | "fundamentals"
  | "ownership"
  | "earnings";
const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "feed", label: "💬 Feed" },
  { id: "bulls", label: "🐂 Bulls" },
  { id: "news", label: "📰 News" },
  { id: "fundamentals", label: "Fundamentals" },
  { id: "ownership", label: "Ownership" },
  { id: "earnings", label: "Earnings" },
];

const crore = (mn: number | null | undefined) =>
  mn == null
    ? "—"
    : `৳${(mn / 10).toLocaleString(undefined, { maximumFractionDigits: 0 })} Cr`;

function QuickStrip({
  f,
  volume,
}: {
  f: Company["fundamentals"];
  volume?: number;
}) {
  const cell = (label: string, value: string) => (
    <div className="flex flex-col items-center px-2">
      <span className="text-[10px] text-muted">{label}</span>
      <span className="text-xs font-semibold tnum">{value}</span>
    </div>
  );
  return (
    <div className="flex justify-between mt-3 pt-3 border-t border-border overflow-x-auto">
      {cell("Mkt Cap", crore(f.market_cap_mn))}
      {cell("Vol", volume != null ? volume.toLocaleString() : "—")}
      {cell("52W H", f.week52_high != null ? `৳${f.week52_high}` : "—")}
      {cell("52W L", f.week52_low != null ? `৳${f.week52_low}` : "—")}
      {cell("P/E", f.pe_ratio != null ? f.pe_ratio.toFixed(1) : "—")}
      {cell("EPS", f.eps != null ? `৳${f.eps}` : "—")}
    </div>
  );
}

export function SymbolPage() {
  const { code = "" } = useParams();
  const sym = code.toUpperCase();
  const { user } = useAuth();
  const [detail, setDetail] = useState<SymbolDetail | null>(null);
  const [topPost, setTopPost] = useState<Post | null>(null);
  const [buzz, setBuzz] = useState<Buzz | null>(null);
  const [company, setCompany] = useState<Company | null>(null);
  const [news, setNews] = useState<NewsItem[] | null>(null);
  const [watched, setWatched] = useState(false);
  const [tab, setTab] = useState<Tab>("overview");
  const discussion = useInfiniteFeed(`${sym}:discussion`, (l, o) =>
    api.feed(sym, undefined, l, o),
  );
  const noteFeed = useInfiniteFeed(`${sym}:notes`, (l, o) =>
    api.feed(sym, "note", l, o),
  );

  useEffect(() => {
    setDetail(null);
    setTopPost(null);
    setBuzz(null);
    setCompany(null);
    setNews(null);
    api
      .symbol(sym)
      .then(setDetail)
      .catch(() => setDetail(null));
    api
      .news(sym)
      .then(setNews)
      .catch(() => setNews([]));
    api
      .topPost(sym)
      .then(setTopPost)
      .catch(() => setTopPost(null));
    api
      .buzz(sym)
      .then(setBuzz)
      .catch(() => setBuzz(null));
    api
      .company(sym)
      .then(setCompany)
      .catch(() => setCompany(null));
    api.recordView(sym).catch(() => {}); // internal analytics; fire-and-forget
    if (user)
      api
        .watchlist()
        .then((w) => setWatched(w.some((i) => i.symbol.code === sym)));
  }, [sym, user]);

  const toggleWatch = async () => {
    if (watched) await api.watchRemove(sym);
    else await api.watchAdd(sym);
    setWatched(!watched);
    setBuzz((b) =>
      b ? { ...b, watchers: b.watchers + (watched ? -1 : 1) } : b,
    );
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
            {buzz && (
              <div className="text-xs text-muted mt-0.5">
                👁 {buzz.watchers.toLocaleString()} watching
                {buzz.watchers_delta_7d != null && (
                  <span
                    className={
                      buzz.watchers_delta_7d >= 0 ? "text-up" : "text-down"
                    }
                  >
                    {" "}
                    ({buzz.watchers_delta_7d >= 0 ? "+" : ""}
                    {buzz.watchers_delta_7d} this week)
                  </span>
                )}
              </div>
            )}
          </div>
          {user && (
            <button
              onClick={toggleWatch}
              className={`ml-auto text-sm px-3 py-1.5 rounded-full border ${
                watched
                  ? "text-accent border-accent bg-accent/10"
                  : "text-muted border-border"
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
              <div>
                H {q.high} · L {q.low}
              </div>
              <div>Vol {q.volume.toLocaleString()}</div>
            </div>
          </div>
        ) : (
          <div className="text-muted text-sm mt-2">No quote yet.</div>
        )}
        <div className="text-[10px] text-muted mt-2">
          ⏱ delayed · as of {new Date(q?.as_of ?? "").toLocaleString()}
        </div>
        {buzz?.attention === "rising" && (
          <div className="mt-2 inline-flex items-center gap-1 text-xs text-accent bg-accent/10 rounded-full px-2 py-0.5 w-fit">
            🔊 Attention rising
            {buzz.chatter_x ? ` · ${buzz.chatter_x}× usual chatter` : ""}
          </div>
        )}
        {company && <QuickStrip f={company.fundamentals} volume={q?.volume} />}
      </div>

      {/* tab bar */}
      <div className="flex gap-2 overflow-x-auto pb-1">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`whitespace-nowrap text-sm font-semibold px-3 py-1.5 rounded-full border ${
              tab === t.id
                ? "text-accent border-accent bg-accent/10"
                : "text-muted border-border"
            }`}
          >
            {t.label}
            {t.id === "bulls" && noteFeed.items.length
              ? ` (${noteFeed.items.length})`
              : ""}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <>
          <PlainReadCard code={sym} />
          <DigestPanel code={sym} />
          <PulseGauges code={sym} />
          <CandleChart code={sym} />
          <Technicals code={sym} />
          <KeyLevels code={sym} />
          <BeforeYouTrade />
        </>
      )}

      {tab === "feed" && (
        <>
          {topPost && (
            <div className="flex flex-col gap-2">
              <div className="text-accent font-semibold text-sm">
                🔥 Most discussed
              </div>
              <PostCard post={topPost} />
            </div>
          )}
          {user ? (
            <Composer
              initial={`$${sym} `}
              onPosted={(p) => discussion.setItems((c) => [p, ...c])}
            />
          ) : (
            <Link
              to="/me"
              className="block text-center text-sm text-accent bg-surface border border-border rounded-2xl py-3"
            >
              Log in to post about ${sym} →
            </Link>
          )}
          {discussion.items.map((p) => (
            <PostCard key={p.id} post={p} />
          ))}
          {discussion.loading && <Spinner />}
          {!discussion.loading && discussion.items.length === 0 && (
            <Empty>No posts about ${sym} yet.</Empty>
          )}
          <div ref={discussion.sentinelRef} />
        </>
      )}

      {tab === "bulls" && (
        <>
          {noteFeed.items.map((p) => (
            <PostCard key={p.id} post={p} />
          ))}
          {noteFeed.loading && <Spinner />}
          {!noteFeed.loading && noteFeed.items.length === 0 && (
            <Empty>
              No data notes for ${sym} yet — they appear as the stock moves.
            </Empty>
          )}
          <div ref={noteFeed.sentinelRef} />
        </>
      )}

      {tab === "news" &&
        (news === null ? <Spinner /> : <NewsPanel items={news} />)}
      {tab === "fundamentals" &&
        (company ? (
          <FundamentalsPanel f={company.fundamentals} />
        ) : (
          <Spinner />
        ))}
      {tab === "ownership" &&
        (company ? <OwnershipPanel o={company.ownership} /> : <Spinner />)}
      {tab === "earnings" &&
        (company ? (
          <EarningsPanel
            earnings={company.earnings}
            dividends={company.dividends}
          />
        ) : (
          <Spinner />
        ))}
    </div>
  );
}
