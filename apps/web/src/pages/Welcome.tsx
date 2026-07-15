import { useEffect, useMemo, useState } from "react";
import { CompanyLogo } from "../components/CompanyLogo";
import { useSeo } from "../components/Seo";
import { Spinner } from "../components/ui";
import { trackProductEvent } from "../lib/analytics";
import { api, type Sector, type SymbolOut } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useLang } from "../lib/i18n";
import { useNavigate } from "../lib/nav";

// No fixed pick-count target: withdrawn 2026-07-15 (was 10) after user feedback that it read as
// a requirement rather than a nudge. "Activated" now just means "added at least one stock" —
// see finish() below. Keep this version string bumped if that definition changes again, so past
// and future watchlist_activated events stay distinguishable in analytics.
const ACTIVATION_VERSION = "watchlist-open-v1";
const STOCKS_SHOWN = 24;

const SECTOR_ICONS: Record<string, string> = {
  Bank: "🏦",
  "Financial Institutions": "▣",
  Insurance: "◆",
  "Fuel & Power": "⚡",
  Pharmaceuticals: "+",
  "Pharmaceuticals & Chemicals": "+",
  Textile: "▥",
  Engineering: "⚙",
  "Food & Allied": "○",
  Cement: "▰",
  Telecommunication: "▤",
  IT: "⌘",
  "IT Sector": "⌘",
};

export function Welcome() {
  const { user } = useAuth();
  const { lang } = useLang();
  const bn = lang === "bn";
  useSeo({ noindex: true });
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [sectors, setSectors] = useState<Sector[] | null>(null);
  const [symbols, setSymbols] = useState<SymbolOut[]>([]);
  const [pickedSectors, setPickedSectors] = useState<Set<string>>(new Set());
  const [pickedStocks, setPickedStocks] = useState<Set<string>>(new Set());
  const [existingStocks, setExistingStocks] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    Promise.allSettled([api.sectors(), api.symbols(500), api.watchlist()]).then((results) => {
      const [sectorResult, symbolResult, watchResult] = results;
      setSectors(sectorResult.status === "fulfilled" ? sectorResult.value : []);
      if (symbolResult.status === "fulfilled") setSymbols(symbolResult.value);
      if (watchResult.status === "fulfilled") {
        const watched = new Set(watchResult.value.map((item) => item.symbol.code));
        setExistingStocks(watched);
        setPickedStocks(watched);
      }
    });
    trackProductEvent("onboarding_started", { source: "post_register" });
  }, []);

  useEffect(() => {
    if (!user) navigate("/me?mode=register&next=/welcome", { replace: true });
  }, [user, navigate]);

  const candidates = useMemo(() => {
    const q = query.trim().toLowerCase();
    return symbols
      .filter((symbol) => symbol.is_active)
      .filter(
        (symbol) =>
          pickedSectors.size === 0 ||
          (symbol.sector != null && pickedSectors.has(symbol.sector)),
      )
      .filter(
        (symbol) =>
          !q ||
          symbol.code.toLowerCase().includes(q) ||
          symbol.name_en.toLowerCase().includes(q) ||
          symbol.name_bn?.includes(q),
      )
      .sort((a, b) => Number(existingStocks.has(b.code)) - Number(existingStocks.has(a.code)))
      .slice(0, STOCKS_SHOWN);
  }, [symbols, pickedSectors, query, existingStocks]);

  const toggleSector = (sector: string) => {
    setPickedSectors((current) => {
      const next = new Set(current);
      if (next.has(sector)) next.delete(sector);
      else next.add(sector);
      return next;
    });
  };

  const toggleStock = (code: string) => {
    setPickedStocks((current) => {
      const next = new Set(current);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  };

  const continueStep = () => {
    trackProductEvent("onboarding_step_completed", {
      step: step + 1,
      watch_count: pickedStocks.size,
    });
    setStep((current) => current + 1);
  };

  const skip = () => {
    trackProductEvent("onboarding_skipped", { step: step + 1, watch_count: pickedStocks.size });
    navigate("/", { replace: true });
  };

  const finish = async () => {
    setSaving(true);
    const additions = [...pickedStocks].filter((code) => !existingStocks.has(code));
    const results = await Promise.allSettled(additions.map((code) => api.watchAdd(code)));
    const added = results.filter((result) => result.status === "fulfilled").length;
    const finalCount = existingStocks.size + added;
    // No fixed target: any real watchlist (>=1 stock) counts as activated.
    if (finalCount >= 1) {
      await trackProductEvent("watchlist_activated", {
        source: "onboarding",
        watch_count: finalCount,
        activation_version: ACTIVATION_VERSION,
      });
    }
    navigate("/watchlist", { replace: true });
  };

  const title = step === 0
    ? bn ? "যে খাতগুলো আপনি অনুসরণ করেন" : "Choose the sectors you follow"
    : step === 1
      ? bn ? "শেয়ার বাছুন" : "Pick stocks to follow"
      : bn ? "আপনার রিসার্চ তালিকা প্রস্তুত" : "Your research list is ready";
  const body = step === 0
    ? bn ? "পছন্দের খাত বাছলে প্রাসঙ্গিক শেয়ার খুঁজে পাওয়া সহজ হবে।" : "This narrows the stock list to the areas relevant to you."
    : step === 1
      ? bn ? "এই শেয়ারগুলোর গুরুত্বপূর্ণ ঘোষণা, মালিকানা ও দামের পরিবর্তন আপনার অ্যালার্টে আসবে।" : "Material disclosures, ownership and price changes for these names will flow into your alerts."
      : bn ? `${pickedStocks.size}টি শেয়ার এক জায়গায় থাকবে। নতুন তথ্য এলে আবার ফিরে আসুন।` : `${pickedStocks.size} stocks will stay in one place. Return when new evidence arrives.`;

  return (
    <div className="flex flex-col gap-4 pt-2">
      <header className="px-1">
        <div className="flex items-center justify-between text-[10px] font-semibold uppercase tracking-wide text-muted">
          <span>{bn ? "ওয়াচলিস্ট সেটআপ" : "Watchlist setup"}</span>
          <span>{step + 1} / 3</span>
        </div>
        <div className="mt-2 grid grid-cols-3 gap-1">
          {[0, 1, 2].map((index) => (
            <span key={index} className={`h-1 rounded-full ${index <= step ? "bg-accent" : "bg-border"}`} />
          ))}
        </div>
        <h1 className="mt-4 text-lg font-bold">{title}</h1>
        <p className="mt-1 text-xs leading-relaxed text-muted">{body}</p>
      </header>

      {step === 0 && (sectors === null ? <Spinner /> : (
        <div className="grid grid-cols-2 gap-2">
          {sectors.map((sector) => (
            <button
              key={sector.sector}
              type="button"
              onClick={() => toggleSector(sector.sector)}
              className={`flex min-h-11 items-center gap-2 rounded-lg border px-3 py-2 text-left text-xs font-semibold ${
                pickedSectors.has(sector.sector)
                  ? "border-accent bg-accent/10 text-accent"
                  : "border-border bg-surface text-text"
              }`}
            >
              <span className="w-5 text-center text-sm">{SECTOR_ICONS[sector.sector] ?? "▦"}</span>
              <span className="min-w-0 break-words">{sector.sector}</span>
            </button>
          ))}
        </div>
      ))}

      {step === 1 && (
        <>
          <div className="sticky z-10 flex items-center gap-2 bg-bg py-1" style={{ top: "var(--app-header-h)" }}>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={bn ? "টিকার বা কোম্পানি খুঁজুন" : "Search ticker or company"}
              className="min-w-0 flex-1 rounded-lg border border-border bg-surface px-3 py-2 text-sm outline-none focus:border-accent"
            />
            {/* Plain running count, no target denominator — picking any number (including
                none, via Skip below) is a complete choice, not partial progress toward a goal. */}
            <span className={`min-w-16 text-center text-xs font-bold ${pickedStocks.size ? "text-up" : "text-muted"}`}>
              {bn ? `${pickedStocks.size}টি বাছাই করা হয়েছে` : `${pickedStocks.size} selected`}
            </span>
          </div>
          <div className="divide-y divide-border border-y border-border">
            {candidates.map((symbol) => (
              <button
                key={symbol.code}
                type="button"
                onClick={() => toggleStock(symbol.code)}
                className="flex w-full items-center gap-2.5 py-2.5 text-left"
              >
                <CompanyLogo code={symbol.code} size={30} />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-bold">${symbol.code}</div>
                  <div className="truncate text-[11px] text-muted">
                    {bn && symbol.name_bn ? symbol.name_bn : symbol.name_en} · {symbol.sector}
                  </div>
                </div>
                <span className={`grid h-7 w-7 shrink-0 place-items-center rounded-full border text-sm ${
                  pickedStocks.has(symbol.code)
                    ? "border-accent bg-accent text-bg"
                    : "border-border text-muted"
                }`}>
                  {pickedStocks.has(symbol.code) ? "✓" : "+"}
                </span>
              </button>
            ))}
          </div>
        </>
      )}

      {step === 2 && (
        <div className="border-y border-border py-2">
          {[
            bn ? "অফিসিয়াল ঘোষণা ও আয়ের আপডেট" : "Official disclosures and earnings updates",
            bn ? "মালিকানা ও অস্বাভাবিক বাজারের পরিবর্তন" : "Ownership and unusual market changes",
            bn ? "আপনার নির্ধারিত দামের অ্যালার্ট" : "Price levels you choose to monitor",
          ].map((item) => (
            <div key={item} className="flex items-center gap-2 py-2 text-sm">
              <span className="text-up">✓</span>
              <span>{item}</span>
            </div>
          ))}
          <p className="mt-2 text-[10px] leading-relaxed text-muted">
            {bn ? "অ্যালার্ট তথ্যভিত্তিক এবং বিলম্বিত হতে পারে। এটি কেনা-বেচার পরামর্শ নয়।" : "Alerts are descriptive and may be delayed. They are not buy or sell recommendations."}
          </p>
        </div>
      )}

      <button
        type="button"
        onClick={step < 2 ? continueStep : finish}
        disabled={saving || (step === 0 && pickedSectors.size === 0) || (step === 1 && pickedStocks.size === 0)}
        className="mx-1 rounded-lg bg-accent py-3 text-sm font-bold text-bg disabled:opacity-40"
      >
        {saving
          ? "…"
          : step === 0
            ? bn ? "শেয়ার বাছুন →" : "Choose stocks →"
            : step === 1
              ? bn ? "তালিকা যাচাই করুন →" : "Review the list →"
              : bn ? "ওয়াচলিস্ট দেখুন" : "View watchlist"}
      </button>
      <button type="button" onClick={skip} className="py-1 text-xs text-muted hover:text-text">
        {bn ? "এখন বাদ দিন" : "Skip for now"}
      </button>
    </div>
  );
}
