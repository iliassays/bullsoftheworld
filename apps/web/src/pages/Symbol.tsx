import { useEffect, useState } from "react";
import { CompanyLogo } from "../components/CompanyLogo";
import { useParams } from "react-router-dom";
import { Link } from "../lib/nav";
import {
  api,
  type Bar,
  type Buzz,
  type Company,
  type InstitutionalActivity,
  type NewsItem,
  type Post,
  type SymbolDetail,
} from "../lib/api";
import { useAuth } from "../lib/auth";
import { useLang } from "../lib/i18n";
import { useTenantConfig } from "../lib/tenant";
import { formatCurrencyMillions } from "../lib/market";
import { formatMarketDateTime } from "../lib/time";
import { useInfiniteFeed } from "../lib/useInfiniteFeed";
import { CandleChart } from "../components/CandleChart";
import { Composer } from "../components/Composer";
import {
  EarningsPanel,
  FinancialHealthPanel,
  FundamentalsPanel,
  NewsPanel,
  OwnershipPanel,
} from "../components/CompanyPanels";
import { InstitutionalHoldingsPanel } from "../components/InstitutionalHoldingsPanel";
import { BeforeYouTrade } from "../components/BeforeYouTrade";
import { useSeo, breadcrumbJsonLd } from "../components/Seo";
import { KeyLevels } from "../components/KeyLevels";
import { InvestorLensCard } from "../components/InvestorLensCard";
import { PlainReadCard } from "../components/PlainReadCard";
import { PriceAlertSheet } from "../components/PriceAlertSheet";
import { ResearchCard } from "../components/ResearchCard";
import { ScorecardCard } from "../components/ScorecardCard";
import { PostCard } from "../components/PostCard";
import { RangeBar } from "../components/RangeBar";
import { Sparkline } from "../components/Sparkline";
import { Technicals } from "../components/Technicals";
import { Empty, Pct, Spinner, taka } from "../components/ui";

// Redesign 2026-07: 8 tabs → 6. Community = discussion + desk notes in one stream (the /posts
// feed for a code already interleaves both); Financials = fundamentals + earnings + dividends.
type Tab = "overview" | "lens" | "community" | "news" | "financials" | "ownership";
const TABS: { id: Tab; icon?: string; key: string }[] = [
  { id: "overview", key: "tab.overview" },
  { id: "lens", icon: "🧠", key: "tab.investorLens" },
  { id: "community", icon: "💬", key: "tab.community" },
  { id: "news", icon: "📰", key: "tab.news" },
  { id: "financials", key: "tab.financials" },
  { id: "ownership", key: "tab.ownership" },
];

function QuickStrip({
  f,
  volume,
  price,
}: {
  f: Company["fundamentals"];
  volume?: number;
  price?: number;
}) {
  const { t } = useLang();
  // A stat with an optional tiny meaning-tag underneath, so the number is interpretable.
  const cell = (label: string, value: string, tag?: string) => (
    <div className="flex flex-col items-center px-2 shrink-0">
      <span className="text-[10px] text-muted">{label}</span>
      <span className="text-xs font-semibold tnum">{value}</span>
      {tag && <span className="text-[9px] text-muted leading-tight">{tag}</span>}
    </div>
  );

  const peTag =
    f.pe_vs_sector == null
      ? undefined
      : f.pe_vs_sector < 0.9
        ? t("tag.cheaperSector")
        : f.pe_vs_sector > 1.1
          ? t("tag.pricierSector")
          : t("tag.inlineSector");
  const volTag =
    volume != null && f.avg_volume_20
      ? `${(volume / f.avg_volume_20).toFixed(1)}× ${t("normal")}`
      : undefined;
  const freeFloat =
    f.free_float_cap_mn != null && f.market_cap_mn
      ? `${((f.free_float_cap_mn / f.market_cap_mn) * 100).toFixed(0)}%`
      : "—";

  return (
    <>
      <div className="flex justify-between mt-3 pt-3 border-t border-border overflow-x-auto">
        {cell(t("stat.mktCap"), formatCurrencyMillions(f.market_cap_mn))}
        {cell(t("stat.vol"), volume != null ? volume.toLocaleString() : "—", volTag)}
        {cell(t("stat.pe"), f.pe_ratio != null ? f.pe_ratio.toFixed(1) : "—", peTag)}
        {cell(t("stat.eps"), f.eps != null ? taka(f.eps) : "—")}
        {cell(t("stat.freeFloat"), freeFloat)}
      </div>
      {f.week52_low != null && f.week52_high != null && price != null && (
        <RangeBar low={f.week52_low} high={f.week52_high} value={price} />
      )}
    </>
  );
}

export function SymbolPage() {
  const { code = "" } = useParams();
  const sym = code.toUpperCase();
  const { user } = useAuth();
  const { t, lang } = useLang();
  const { config } = useTenantConfig();
  const [detail, setDetail] = useState<SymbolDetail | null>(null);
  const [topPost, setTopPost] = useState<Post | null>(null);
  const [buzz, setBuzz] = useState<Buzz | null>(null);
  const [company, setCompany] = useState<Company | null>(null);
  const [institutional, setInstitutional] = useState<InstitutionalActivity | null>(null);
  const [news, setNews] = useState<NewsItem[] | null>(null);
  const [bars, setBars] = useState<Bar[]>([]);
  const [watched, setWatched] = useState(false);
  const [alertsOpen, setAlertsOpen] = useState(false);
  const [tab, setTab] = useState<Tab>("overview");
  const discussion = useInfiniteFeed(`${sym}:discussion`, (l, o) =>
    api.feed(sym, undefined, l, o),
  );

  useEffect(() => {
    setDetail(null);
    setTopPost(null);
    setBuzz(null);
    setCompany(null);
    setInstitutional(null);
    setNews(null);
    setBars([]);
    api
      .symbol(sym)
      .then(setDetail)
      .catch(() => setDetail(null));
    api
      .bars(sym, 90)
      .then(setBars)
      .catch(() => setBars([]));
    if (config.features.official_disclosures) {
      api
        .news(sym)
        .then(setNews)
        .catch(() => setNews([]));
    } else {
      setNews([]);
    }
    api
      .topPost(sym)
      .then(setTopPost)
      .catch(() => setTopPost(null));
    api
      .buzz(sym)
      .then(setBuzz)
      .catch(() => setBuzz(null));
    if (config.features.company_fundamentals) {
      api
        .company(sym)
        .then(setCompany)
        .catch(() => setCompany(null));
    }
    if (config.features.institutional_holdings) {
      api
        .institutionalHoldings(sym)
        .then(setInstitutional)
        .catch(() => setInstitutional(null));
    }
    api.recordView(sym).catch(() => {}); // internal analytics; fire-and-forget
    if (user)
      api
        .watchlist()
        .then((w) => setWatched(w.some((i) => i.symbol.code === sym)));
  }, [
    sym,
    user,
    config.features.company_fundamentals,
    config.features.institutional_holdings,
    config.features.official_disclosures,
  ]);

  const toggleWatch = async () => {
    if (watched) await api.watchRemove(sym);
    else await api.watchAdd(sym);
    setWatched(!watched);
    setBuzz((b) =>
      b ? { ...b, watchers: b.watchers + (watched ? -1 : 1) } : b,
    );
  };

  // Per-stock head. Computed from whatever's loaded (name/price/sector); falls back to the raw
  // ticker before `detail` arrives so the hook runs unconditionally (before the early return).
  const seoName =
    (lang === "bn" ? detail?.symbol.name_bn || detail?.symbol.name_en : detail?.symbol.name_en) ||
    sym;
  const seoSector = detail?.symbol.sector;
  const priceTxt =
    detail?.quote?.ltp != null
      ? `${config.currency_symbol}${detail.quote.ltp.toLocaleString(undefined, {
          maximumFractionDigits: config.price_decimals,
        })}`
      : "";
  const exchange = config.exchange_code;
  const brand = config.brand_name;
  const hasResearchData =
    config.features.company_fundamentals ||
    config.features.interpreted_analytics ||
    config.features.official_disclosures;
  const marketUi = {
    market: config.market,
    exchangeCode: config.exchange_code,
    currencyCode: config.currency_code,
    currencySymbol: config.currency_symbol,
    timezone: config.timezone,
    timezoneLabel: config.timezone_label,
    priceDecimals: config.price_decimals,
    compactMoneyUnits: config.compact_money_units.map((u) => ({
      minValueMn: u.min_value_mn,
      divisorMn: u.divisor_mn,
      suffix: u.suffix,
      decimals: u.decimals,
    })),
    marketCapMoneyUnits: config.market_cap_money_units.map((u) => ({
      minValueMn: u.min_value_mn,
      divisorMn: u.divisor_mn,
      suffix: u.suffix,
      decimals: u.decimals,
    })),
  };
  const tabs = TABS.filter(
    (candidate) =>
      (candidate.id !== "ownership" ||
        config.features.shareholding_breakdown ||
        config.features.institutional_holdings) &&
      (candidate.id !== "lens" || config.features.interpreted_analytics) &&
      (candidate.id !== "financials" || config.features.company_fundamentals) &&
      (candidate.id !== "news" || config.features.official_disclosures),
  );
  useSeo({
    title:
      lang === "bn"
        ? `${seoName} (${sym}) শেয়ার দাম ${priceTxt} — ${exchange} | ${brand}`
        : `${seoName} (${sym}) share price ${priceTxt} — ${exchange} | ${brand}`,
    description:
      lang === "bn"
        ? hasResearchData
          ? `${seoName}-এর সর্বশেষ শেয়ার দাম, ফান্ডামেন্টাল, চার্ট বিশ্লেষণ, অফিশিয়াল খবর ও কমিউনিটি আলোচনা${seoSector ? ` · খাত: ${seoSector}` : ""}। বর্ণনামূলক তথ্য, বিনিয়োগ পরামর্শ নয়।`
          : `${seoName}-এর সর্বশেষ শেয়ার দাম, দামের ইতিহাস ও কমিউনিটি আলোচনা${seoSector ? ` · খাত: ${seoSector}` : ""}। বর্ণনামূলক তথ্য, বিনিয়োগ পরামর্শ নয়।`
        : hasResearchData
          ? `${seoName} latest share price, fundamentals, chart analysis, official news and community discussion${seoSector ? ` · Sector: ${seoSector}` : ""}. Descriptive data, not investment advice.`
          : `${seoName} latest share price, price history and community discussion${seoSector ? ` · Sector: ${seoSector}` : ""}. Descriptive data, not investment advice.`,
    jsonLd: breadcrumbJsonLd(lang, [
      { name: lang === "bn" ? "হোম" : "Home", path: "/" },
      { name: `${seoName} (${sym})`, path: `/s/${sym}` },
    ]),
  });

  if (detail === null) return <Spinner />;
  const q = detail.quote;

  return (
    <div className="flex flex-col gap-3">
      <div className="bg-surface border border-border rounded-2xl p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <CompanyLogo code={sym} size={40} />
            <div className="min-w-0">
              <div className="text-xl font-bold">${sym}</div>
              <div className="text-xs text-muted truncate">{detail.symbol.name_en}</div>
            </div>
          </div>
          {/* StockTwits-style: compact watchers count + a small +/✓ follow toggle. */}
          <div className="flex items-center gap-2 shrink-0">
            {buzz && (
              <span
                className="flex items-center gap-1 text-sm text-muted tnum"
                title={t("watching")}
              >
                <span aria-hidden>👥</span>
                {buzz.watchers.toLocaleString()}
                {buzz.watchers_delta_7d != null && buzz.watchers_delta_7d !== 0 && (
                  <span
                    className={buzz.watchers_delta_7d > 0 ? "text-up" : "text-down"}
                  >
                    {buzz.watchers_delta_7d > 0 ? "+" : ""}
                    {buzz.watchers_delta_7d}
                  </span>
                )}
              </span>
            )}
            {user && config.features.price_alerts && (
              <button
                onClick={() => setAlertsOpen((v) => !v)}
                aria-label={t("pa.title")}
                title={t("pa.title")}
                className={`grid h-8 w-8 place-items-center rounded-full border text-sm leading-none transition ${
                  alertsOpen
                    ? "border-accent bg-accent/10 text-accent"
                    : "border-border text-muted hover:border-accent hover:text-accent"
                }`}
              >
                🔔
              </button>
            )}
            {user ? (
              <button
                onClick={toggleWatch}
                aria-label={watched ? t("btn.watching") : t("btn.watch")}
                title={watched ? t("btn.watching") : t("btn.watch")}
                className={`grid h-8 w-8 place-items-center rounded-full border text-lg leading-none transition ${
                  watched
                    ? "border-accent bg-accent/10 text-accent"
                    : "border-border text-muted hover:border-accent hover:text-accent"
                }`}
              >
                {watched ? "✓" : "+"}
              </button>
            ) : (
              // Logged out: tapping routes to login (like post reactions).
              <Link
                to="/me"
                aria-label={t("btn.watch")}
                title={t("btn.watchLogin")}
                className="grid h-8 w-8 place-items-center rounded-full border border-border text-lg leading-none text-muted hover:border-accent hover:text-accent"
              >
                +
              </Link>
            )}
          </div>
        </div>
        {q ? (
          <div className="mt-3 flex flex-wrap items-end gap-x-3 gap-y-1">
            <div className="text-2xl font-bold tnum">{taka(q.ltp)}</div>
            <div className="text-sm font-semibold pb-1">
              <Pct value={q.change_pct} />
            </div>
            {bars.length > 1 && (
              <span className="hidden pb-1 min-[430px]:inline">
                <Sparkline data={bars.map((b) => b.close)} width={84} height={30} />
              </span>
            )}
            <div className="flex w-full justify-between text-left text-[11px] text-muted tnum min-[430px]:ml-auto min-[430px]:block min-[430px]:w-auto min-[430px]:text-right min-[430px]:text-xs">
              <div>
                H {q.high.toFixed(config.price_decimals)} · L {q.low.toFixed(config.price_decimals)}
              </div>
              <div>Vol {q.volume.toLocaleString()}</div>
            </div>
          </div>
        ) : (
          <div className="text-muted text-sm mt-2">{t("noQuote")}</div>
        )}
        <div className="text-[10px] text-muted mt-2">
          ⏱ {t("delayedAsOf")} {formatMarketDateTime(q?.as_of, marketUi)}
        </div>
        {buzz?.attention === "rising" && (
          <div className="mt-2 inline-flex items-center gap-1 text-xs text-accent bg-accent/10 rounded-full px-2 py-0.5 w-fit">
            🔊 {t("attentionRising")}
            {buzz.chatter_x ? ` · ${buzz.chatter_x}× ${t("usualChatter")}` : ""}
          </div>
        )}
        {company && (
          <QuickStrip f={company.fundamentals} volume={q?.volume} price={q?.ltp} />
        )}
      </div>

      {alertsOpen && config.features.price_alerts && (
        <PriceAlertSheet code={sym} onClose={() => setAlertsOpen(false)} />
      )}

      {/* tab bar — pinned below the app header so switching tabs never needs a scroll-up */}
      <div
        className="sticky z-10 -mx-3 px-3 py-1.5 bg-bg/95 backdrop-blur flex gap-2 overflow-x-auto"
        style={{ top: "var(--app-header-h, 96px)" }}
      >
        {tabs.map((tb) => (
          <button
            key={tb.id}
            onClick={() => setTab(tb.id)}
            className={`whitespace-nowrap text-sm font-semibold px-3 py-1.5 rounded-full border ${
              tab === tb.id
                ? "text-accent border-accent bg-accent/10"
                : "text-muted border-border"
            }`}
          >
            {tb.icon ? `${tb.icon} ` : ""}
            {t(tb.key)}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <>
          {/* Overview is the fast research path: chart, grounded read, evidence, levels, checklist. */}
          <CandleChart code={sym} />
          {config.features.interpreted_analytics && (
            <>
              <PlainReadCard code={sym} />
              <ResearchCard code={sym} />
              <KeyLevels code={sym} />
            </>
          )}
          <BeforeYouTrade />
        </>
      )}

      {tab === "lens" && (
        <>
          <ScorecardCard code={sym} />
          <InvestorLensCard code={sym} />
          <Technicals code={sym} />
        </>
      )}

      {tab === "community" && (
        <>
          {topPost && (
            <div className="flex flex-col gap-2">
              <div className="font-semibold text-sm">
                🔥 Most discussed
              </div>
              <PostCard post={topPost} />
            </div>
          )}
          {user ? (
            <Composer
              initial={`$${sym} `}
              routeCode={sym}
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

      {tab === "news" &&
        (news === null ? <Spinner /> : <NewsPanel items={news} ltp={q?.ltp} />)}
      {tab === "financials" &&
        (company ? (
          <>
            <FundamentalsPanel f={company.fundamentals} earnings={company.earnings} />
            <FinancialHealthPanel company={company} />
            <EarningsPanel
              earnings={company.earnings}
              dividends={company.dividends}
              f={company.fundamentals}
            />
          </>
        ) : (
          <Spinner />
        ))}
      {tab === "ownership" &&
        (config.features.institutional_holdings ? (
          institutional ? <InstitutionalHoldingsPanel data={institutional} /> : <Spinner />
        ) : company ? (
          <OwnershipPanel o={company.ownership} />
        ) : (
          <Spinner />
        ))}
    </div>
  );
}
