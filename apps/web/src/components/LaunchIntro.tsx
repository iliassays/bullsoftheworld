import { useEffect, useState } from "react";
import { trackProductEvent } from "../lib/analytics";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useLang } from "../lib/i18n";
import { Link } from "../lib/nav";
import { useTenantConfig } from "../lib/tenant";

const ACTIVATION_TARGET = 10;

export function LaunchIntro() {
  const { user } = useAuth();
  const { lang } = useLang();
  const { config } = useTenantConfig();
  const [watchCount, setWatchCount] = useState<number | null>(null);
  const bn = lang === "bn";

  useEffect(() => {
    if (!user) {
      setWatchCount(null);
      return;
    }
    api
      .watchlist()
      .then((items) => setWatchCount(items.length))
      .catch(() => setWatchCount(null));
  }, [user]);

  if (user && (watchCount == null || watchCount >= ACTIVATION_TARGET)) return null;

  if (user) {
    const currentWatchCount = watchCount ?? 0;
    return (
      <section className="border-y border-border bg-surface/60 px-4 py-3" aria-label={bn ? "ওয়াচলিস্ট সেটআপ" : "Watchlist setup"}>
        <div className="flex items-center gap-3">
          <div className="min-w-0 flex-1">
            <div className="text-sm font-bold">
              {bn ? "১০টি শেয়ার ট্র্যাক করে শুরু করুন" : "Start by tracking 10 stocks"}
            </div>
            <div className="mt-0.5 text-[11px] leading-relaxed text-muted">
              {bn
                ? `${currentWatchCount}/${ACTIVATION_TARGET} যোগ হয়েছে। গুরুত্বপূর্ণ ঘোষণা, মালিকানা ও দামের পরিবর্তন এক জায়গায় দেখুন।`
                : `${currentWatchCount}/${ACTIVATION_TARGET} added. Bring material disclosures, ownership and price changes into one place.`}
            </div>
          </div>
          <Link
            to="/welcome"
            onClick={() =>
              trackProductEvent("onboarding_started", {
                source: "home_activation",
                watch_count: currentWatchCount,
              })
            }
            className="shrink-0 rounded-lg bg-accent px-3 py-2 text-xs font-bold text-bg"
          >
            {bn ? "সেটআপ" : "Set up"}
          </Link>
        </div>
        <div className="mt-2 h-1 overflow-hidden rounded-full bg-border">
          <div
            className="h-full bg-accent"
            style={{ width: `${Math.min(100, (currentWatchCount / ACTIVATION_TARGET) * 100)}%` }}
          />
        </div>
      </section>
    );
  }

  const exchange = bn ? config.exchange_name_bn || config.exchange_name : config.exchange_name;
  const outcomes = bn
    ? [
        ["কারণ বুঝুন", "অফিসিয়াল খবর ও বাজারের আচরণ আলাদা করে দেখুন"],
        ["ঝুঁকি যাচাই করুন", "তারল্য, মূল্যায়ন, মালিকানা ও অতিরিক্ত ভিড় দেখুন"],
        ["পরিবর্তন মিস করবেন না", "নিজের শেয়ারের গুরুত্বপূর্ণ ইভেন্টে অ্যালার্ট পান"],
      ]
    : [
        ["Understand the move", "Separate official evidence from market behaviour"],
        ["Check the risk", "Review liquidity, valuation, ownership and crowding"],
        ["Do not miss a change", "Get alerts for material events in stocks you follow"],
      ];

  return (
    <section className="border-b border-border pb-4" aria-labelledby="launch-heading">
      <div className="px-1 pt-1">
        <div className="text-[10px] font-semibold uppercase tracking-wide text-accent">
          {exchange} {bn ? "রিসার্চ" : "research"}
        </div>
        <h1 id="launch-heading" className="mt-1 text-xl font-extrabold leading-tight">
          {bn ? "লেনদেনের আগে তথ্যটি বুঝুন" : "Understand the evidence before you trade"}
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-muted">
          {bn
            ? "অফিসিয়াল তথ্য, বাজারের সিগন্যাল ও ঝুঁকি সহজ ভাষায়। কোনো টিপস নয়, সিদ্ধান্ত আপনার।"
            : "Official evidence, market signals and risk in plain language. No tips; the decision remains yours."}
        </p>
      </div>

      <div className="mt-3 divide-y divide-border border-y border-border">
        {outcomes.map(([title, body], index) => (
          <div key={title} className="flex gap-3 py-2.5">
            <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full border border-accent/50 text-[11px] font-bold text-accent">
              {index + 1}
            </span>
            <div>
              <div className="text-xs font-bold">{title}</div>
              <div className="mt-0.5 text-[11px] leading-relaxed text-muted">{body}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-3 grid grid-cols-[1fr_auto] gap-2">
        <Link
          to="/me?mode=register&next=/welcome"
          onClick={() =>
            trackProductEvent("click_launch_signup", {
              destination: "register",
              surface: "home_intro",
              market: config.market,
            })
          }
          className="rounded-lg bg-accent px-4 py-2.5 text-center text-sm font-bold text-bg"
        >
          {bn ? "বিনামূল্যে ১০টি শেয়ার ট্র্যাক করুন" : "Track 10 stocks for free"}
        </Link>
        <Link
          to="/ideas"
          aria-label={bn ? "আজকের আইডিয়া দেখুন" : "View today's ideas"}
          title={bn ? "আজকের আইডিয়া" : "Today's ideas"}
          onClick={() =>
            trackProductEvent("click_launch_ideas", {
              destination: "ideas",
              surface: "home_intro",
            })
          }
          className="grid min-w-11 place-items-center rounded-lg border border-border px-3 text-lg text-accent hover:border-accent"
        >
          →
        </Link>
      </div>
      <div className="mt-2 flex items-center justify-between px-1 text-[10px] text-muted">
        <span>{bn ? "কার্ড বা ব্রোকার সংযোগ লাগবে না" : "No card or broker connection required"}</span>
        <Link to="/institutions" className="font-semibold text-accent">
          {bn ? "প্রতিষ্ঠানের জন্য" : "For institutions"}
        </Link>
      </div>
    </section>
  );
}
