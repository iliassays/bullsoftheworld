import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Empty, Pct, Spinner, taka } from "../components/ui";
import { api, type ScannerResponse, type Screen, type ScreenItem } from "../lib/api";
import { useAuth } from "../lib/auth";
import { type Lang, useLang } from "../lib/i18n";
import { Watchlist } from "./Watchlist";

type Tab = "today" | "value" | "watchlist";
type Picked = { board: Screen; item: ScreenItem };

const BOARD_ICON: Record<string, string> = {
  quality_reversal: "🌊",
  active_today: "🔥",
  most_active: "💸",
  value_quality: "⭐",
  dividend_quality: "💵",
};

const BOARD_TEXT: Record<string, Record<Lang, { title: string; desc: string; label: string }>> = {
  quality_reversal: {
    en: {
      title: "Turn Attempts",
      desc: "Beaten-down but profitable names trying to reclaim a short-term level.",
      label: "Turn attempt",
    },
    bn: {
      title: "ঘুরে দাঁড়ানোর চেষ্টা",
      desc: "অনেক পড়েছে, কিন্তু লাভজনক এবং সাম্প্রতিক লেভেল ভাঙার চেষ্টা করছে।",
      label: "টার্ন চেষ্টা",
    },
  },
  active_today: {
    en: {
      title: "Active Today",
      desc: "Unusual volume and turnover versus the stock's own normal pace.",
      label: "Unusual activity",
    },
    bn: {
      title: "আজ অস্বাভাবিক লেনদেন",
      desc: "নিজের স্বাভাবিক লেনদেনের তুলনায় আজ ভলিউম/টার্নওভার বেশি।",
      label: "অস্বাভাবিক লেনদেন",
    },
  },
  most_active: {
    en: {
      title: "Top Turnover",
      desc: "Where the most traded value is today, liquidity-gated.",
      label: "High turnover",
    },
    bn: {
      title: "আজ বেশি টাকার লেনদেন",
      desc: "আজ কোথায় বেশি টাকা ঘুরছে, লিকুইডিটি ফিল্টারসহ।",
      label: "বেশি টার্নওভার",
    },
  },
  value_quality: {
    en: {
      title: "Value + Quality",
      desc: "Cheaper than sector peers with profitability support.",
      label: "Value + quality",
    },
    bn: {
      title: "সস্তা + ভালো মান",
      desc: "খাতের তুলনায় সস্তা, সাথে লাভজনকতার সমর্থন আছে।",
      label: "ভ্যালু + মান",
    },
  },
  dividend_quality: {
    en: {
      title: "Dividend Quality",
      desc: "Cash-yield names with positive earnings context.",
      label: "Dividend check",
    },
    bn: {
      title: "লভ্যাংশ + কভারেজ",
      desc: "নগদ লভ্যাংশের সাথে আয়ের কভারেজ আছে কি না দেখার তালিকা।",
      label: "লভ্যাংশ চেক",
    },
  },
};

function boardText(board: Screen, lang: Lang) {
  return BOARD_TEXT[board.key]?.[lang] ?? { title: board.title, desc: board.description, label: board.title };
}

function metricText(board: Screen, item: ScreenItem, lang: Lang): string {
  if (board.key === "most_active") return lang === "bn" ? `৳${item.value.toFixed(1)}cr` : `Tk ${item.value.toFixed(1)}cr`;
  if (board.value_label === "yield") return `${item.value.toFixed(1)}%`;
  if (board.value_label === "x sector") return `${item.value.toFixed(2)}x`;
  if (board.value_label.includes("%")) return `${item.value.toFixed(0)}%`;
  if (board.value_label === "activity") return lang === "bn" ? "সক্রিয়" : "Active";
  return item.value.toFixed(1);
}

function liquidityText(item: ScreenItem, lang: Lang): string | null {
  if (!item.liquidity) return null;
  if (lang === "bn") {
    if (item.liquidity.includes("Deep")) return "গভীর লিকুইডিটি";
    if (item.liquidity.includes("Tradeable")) return "লেনদেনযোগ্য";
    if (item.liquidity.includes("Watch")) return "অর্ডার সাইজে সতর্কতা";
    if (item.liquidity.includes("Thin")) return "পাতলা লিকুইডিটি";
    if (item.liquidity.includes("Z")) return "Z ঝুঁকি";
  }
  return item.liquidity;
}

function defaultHow(board: Screen, lang: Lang): string {
  if (lang === "bn") {
    if (board.key === "active_today") return "কোথায় লেনদেন অস্বাভাবিক হচ্ছে তা দেখুন, তারপর কারণ যাচাই করুন।";
    if (board.key === "most_active") return "লেনদেন বেশি হলে ঢোকা-বের হওয়া সহজ হতে পারে, কিন্তু দামের দিক দেখুন।";
    if (board.key === "value_quality") return "ভ্যালু shortlist হিসেবে দেখুন; EPS, ঋণ ও খবর যাচাই করুন।";
    if (board.key === "dividend_quality") return "লভ্যাংশের আগে EPS কভারেজ, রেকর্ড ডেট ও পেআউট ইতিহাস দেখুন।";
    return "সম্ভাব্য টার্ন চেষ্টা হিসেবে দেখুন; ভলিউম, খবর ও সাপোর্ট যাচাই করুন।";
  }
  if (board.key === "active_today") return "Use it to see where activity is unusual, then verify the reason.";
  if (board.key === "most_active") return "High turnover may help entry/exit, but check price direction.";
  if (board.key === "value_quality") return "Use it as a value shortlist; verify EPS, debt and news.";
  if (board.key === "dividend_quality") return "Check EPS cover, record date and payout history before trusting yield.";
  return "Use it as a possible turn-attempt list; verify volume, news and support.";
}

function defaultRisk(board: Screen, lang: Lang): string {
  if (lang === "bn") {
    if (board.key === "value_quality") return "সস্তা মানেই ভালো নয়; দুর্বল ব্যবসা হলে value trap হতে পারে।";
    if (board.key === "dividend_quality") return "অতীত লভ্যাংশ ভবিষ্যৎ লভ্যাংশের নিশ্চয়তা নয়।";
    if (board.key === "active_today" || board.key === "most_active") return "অ্যাক্টিভ মানেই দাম বাড়বে নয়; heavy selling-ও হতে পারে।";
    return "অনেক পড়া শেয়ার আরও পড়তে পারে; এটি buy signal নয়।";
  }
  if (board.key === "value_quality") return "Cheap can still be a value trap if earnings weaken.";
  if (board.key === "dividend_quality") return "Past dividend does not guarantee future dividend.";
  if (board.key === "active_today" || board.key === "most_active") return "Active does not mean bullish; heavy selling can also create activity.";
  return "Deeply fallen stocks can keep falling; this is not a buy signal.";
}

function checksFor(board: Screen, item: ScreenItem, lang: Lang): string[] {
  if (item.check_next?.length) return item.check_next;
  if (lang === "bn") {
    if (board.key === "value_quality") return ["EPS ট্রেন্ড", "ঋণ/NAV", "খবর", "সেক্টর তুলনা"];
    if (board.key === "dividend_quality") return ["রেকর্ড ডেট", "EPS কভার", "পেআউট ইতিহাস", "দাম সমন্বয়"];
    if (board.key === "active_today" || board.key === "most_active") return ["খবর", "দামের দিক", "ADTV", "খাত"];
    return ["খবর", "ভলিউম", "সাপোর্ট", "অর্ডার সাইজ"];
  }
  if (board.key === "value_quality") return ["EPS trend", "Debt/NAV", "News", "Sector compare"];
  if (board.key === "dividend_quality") return ["Record date", "EPS cover", "Payout history", "Price adjustment"];
  if (board.key === "active_today" || board.key === "most_active") return ["News", "Price direction", "ADTV", "Sector"];
  return ["News", "Volume", "Support", "Order size"];
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-xl bg-card border border-border px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-muted truncate">{label}</div>
      <div className="mt-0.5 text-sm font-bold text-text truncate tnum">{value}</div>
    </div>
  );
}

function ScannerSheet({ picked, onClose }: { picked: Picked; onClose: () => void }) {
  const { lang, t } = useLang();
  const { board, item } = picked;
  const text = boardText(board, lang);
  const liq = liquidityText(item, lang);
  const checks = checksFor(board, item, lang);
  const how = item.how_to_read || defaultHow(board, lang);
  const risk = item.risk_note || defaultRisk(board, lang);

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/55" onClick={onClose}>
      <div
        className="w-full max-w-md max-h-[86vh] overflow-y-auto rounded-t-2xl border border-border bg-surface shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-4 pb-0">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-[10px] uppercase tracking-wide text-muted">
                {lang === "bn" ? "স্ক্যানার ব্রিফ" : "Scanner brief"}
              </div>
              <div className="mt-0.5 flex items-center gap-2">
                <div className="truncate text-xl font-extrabold">${item.code}</div>
                <span className="shrink-0 rounded-full border border-border bg-card px-2 py-0.5 text-[10px] font-semibold text-accent">
                  {BOARD_ICON[board.key] ?? "📈"} {text.label}
                </span>
              </div>
              <div className="mt-0.5 text-xs text-muted truncate">{item.name || item.code}</div>
            </div>
            <button onClick={onClose} className="px-2 text-sm text-muted">
              {t("common.close")}
            </button>
          </div>

          <div className="mt-3 grid grid-cols-2 gap-2">
            {item.last_close > 0 && <MiniStat label={lang === "bn" ? "দাম" : "Price"} value={taka(item.last_close)} />}
            {item.change_1d != null && (
              <MiniStat
                label="1D"
                value={`${item.change_1d >= 0 ? "+" : ""}${item.change_1d.toFixed(1)}%`}
              />
            )}
            <MiniStat label={text.label} value={metricText(board, item, lang)} />
            {liq && <MiniStat label={lang === "bn" ? "লিকুইডিটি" : "Liquidity"} value={liq} />}
          </div>

          <section className="mt-4 rounded-xl border border-accent/25 bg-accent/8 p-3">
            <div className="text-[10px] uppercase tracking-wide text-muted">
              {lang === "bn" ? "কেন দেখাচ্ছে" : "Why it appears"}
            </div>
            <p className="mt-1 text-sm leading-snug text-text">{item.why || text.desc}</p>
          </section>

          <section className="mt-3 rounded-xl border border-border bg-card/60 p-3">
            <div className="text-[10px] uppercase tracking-wide text-muted">
              {lang === "bn" ? "কীভাবে পড়বেন" : "How to read"}
            </div>
            <p className="mt-1 text-xs leading-snug text-text/90">{how}</p>
            <div className="mt-3 text-[10px] uppercase tracking-wide text-muted">
              {lang === "bn" ? "এরপর যাচাই করুন" : "Verify next"}
            </div>
            <div className="mt-2 grid grid-cols-2 gap-1.5">
              {checks.map((check) => (
                <div key={check} className="flex items-center gap-1.5 text-[11px] text-muted">
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                  <span className="truncate">{check}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="mt-3 rounded-xl border border-border bg-card/40 p-3">
            <div className="text-[10px] uppercase tracking-wide text-muted">
              {lang === "bn" ? "ঝুঁকি ও লেনদেন" : "Risk and execution"}
            </div>
            <p className="mt-1 text-xs leading-snug text-muted">{risk}</p>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {item.adtv_mn != null && (
                <span className="rounded-full border border-border bg-surface px-2.5 py-1 text-[11px] text-muted">
                  ADTV ৳{item.adtv_mn.toFixed(1)}mn
                </span>
              )}
              {item.safe_order_mn != null && (
                <span className="rounded-full border border-border bg-surface px-2.5 py-1 text-[11px] text-muted">
                  {lang === "bn" ? "অর্ডার গাইড" : "Order guide"} ৳{item.safe_order_mn.toFixed(1)}mn
                </span>
              )}
              {item.turnover_mn != null && (
                <span className="rounded-full border border-border bg-surface px-2.5 py-1 text-[11px] text-muted">
                  {lang === "bn" ? "আজ" : "Today"} ৳{item.turnover_mn.toFixed(1)}mn
                </span>
              )}
              {item.category && (
                <span className="rounded-full border border-border bg-surface px-2.5 py-1 text-[11px] text-muted">
                  Cat {item.category}
                </span>
              )}
            </div>
          </section>
        </div>

        <div className="sticky bottom-0 mt-4 border-t border-border bg-surface/95 p-4 backdrop-blur">
          <Link
            to={`/s/${item.code}`}
            className="block rounded-xl bg-accent py-3 text-center text-sm font-extrabold text-bg"
          >
            {lang === "bn" ? `$${item.code}-এর পুরো স্টক পেজ খুলুন` : `Open full stock page for $${item.code}`} →
          </Link>
        </div>
      </div>
    </div>
  );
}

function ScannerRow({ board, item, onPick }: { board: Screen; item: ScreenItem; onPick: () => void }) {
  const { lang } = useLang();
  const text = boardText(board, lang);
  const liq = liquidityText(item, lang);
  return (
    <button onClick={onPick} className="flex w-full items-start gap-3 py-3 text-left">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-extrabold text-sm">${item.code}</span>
          <span className="rounded-full border border-border bg-card px-2 py-0.5 text-[10px] font-semibold text-accent">
            {item.scanner_label || text.label}
          </span>
          {item.category && <span className="text-[10px] text-muted">Cat {item.category}</span>}
        </div>
        <div className="mt-0.5 line-clamp-2 text-[11px] leading-snug text-muted">
          {item.why || text.desc}
        </div>
        {liq && <div className="mt-1 text-[10px] font-semibold text-muted">{liq}</div>}
      </div>
      <div className="shrink-0 text-right tnum">
        {item.last_close > 0 && <div className="text-[13px] font-semibold">{taka(item.last_close)}</div>}
        <div className="text-xs font-semibold">
          {item.change_1d != null ? <Pct value={item.change_1d} /> : <span className="text-muted">{metricText(board, item, lang)}</span>}
        </div>
      </div>
    </button>
  );
}

function BoardCard({ board, onPick }: { board: Screen; onPick: (picked: Picked) => void }) {
  const { lang } = useLang();
  const text = boardText(board, lang);
  return (
    <section className="rounded-2xl border border-border bg-surface p-4">
      <div className="flex items-start gap-2">
        <div className="text-lg">{BOARD_ICON[board.key] ?? "📈"}</div>
        <div className="min-w-0">
          <div className="text-sm font-bold">{text.title}</div>
          <p className="mt-0.5 text-xs leading-relaxed text-muted">{text.desc}</p>
        </div>
      </div>
      <div className="mt-2 flex flex-col divide-y divide-border">
        {board.items.map((item) => (
          <ScannerRow key={item.code} board={board} item={item} onPick={() => onPick({ board, item })} />
        ))}
      </div>
    </section>
  );
}

function Boards({
  tab,
  watched,
  onPick,
}: {
  tab: "today" | "value";
  watched: boolean;
  onPick: (picked: Picked) => void;
}) {
  const { t } = useLang();
  const [data, setData] = useState<ScannerResponse | null>(null);
  useEffect(() => {
    setData(null);
    let live = true;
    api
      .scannerRadar(tab, watched)
      .then((d) => live && setData(d))
      .catch(() => live && setData(null));
    return () => {
      live = false;
    };
  }, [tab, watched]);

  if (!data) return <Spinner />;
  if (data.boards.length === 0) {
    return <Empty>{watched ? t("scanner.emptyWatched") : t("scanner.empty")}</Empty>;
  }
  return (
    <div className="flex flex-col gap-3">
      {data.boards.map((board) => (
        <BoardCard key={board.key} board={board} onPick={onPick} />
      ))}
    </div>
  );
}

export function Scanner() {
  const { t, lang } = useLang();
  const { user } = useAuth();
  const [tab, setTab] = useState<Tab>("today");
  const [watched, setWatched] = useState(false);
  const [picked, setPicked] = useState<Picked | null>(null);

  const seg = (id: Tab, label: string) => (
    <button
      onClick={() => setTab(id)}
      className={`flex-1 rounded-full py-1.5 text-sm font-semibold transition ${
        tab === id ? "bg-accent text-bg" : "text-muted"
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="flex flex-col gap-3">
      <div>
        <div className="text-sm font-bold">{lang === "bn" ? "স্ক্যানার" : "Scanner"}</div>
        <p className="mt-0.5 text-xs leading-snug text-muted">
          {lang === "bn"
            ? "আজ কী অস্বাভাবিক, কোন শেয়ার পড়ে ঘুরতে চাইছে, আর কোনগুলো ভ্যালু হিসেবে দেখার মতো।"
            : "Fast lists for unusual activity, turn attempts, and value names worth studying."}
        </p>
      </div>

      <div className="flex gap-1 rounded-full border border-border bg-surface p-1">
        {seg("today", t("scanner.today"))}
        {seg("value", t("scanner.value"))}
        {seg("watchlist", t("scanner.watchlist"))}
      </div>

      {tab === "watchlist" ? (
        <div className="flex flex-col gap-3">
          {user ? (
            <>
              <Boards tab="today" watched onPick={setPicked} />
              <details className="rounded-2xl border border-border bg-surface p-3">
                <summary className="cursor-pointer text-sm font-semibold text-accent">
                  {lang === "bn" ? "ওয়াচলিস্ট দেখুন" : "View watchlist"}
                </summary>
                <div className="mt-3">
                  <Watchlist />
                </div>
              </details>
            </>
          ) : (
            <Watchlist />
          )}
        </div>
      ) : (
        <>
          {user && (
            <div className="flex items-center gap-2 text-xs">
              <span className="text-muted">{t("scanner.scope")}:</span>
              <button
                onClick={() => setWatched(false)}
                className={`rounded-full border px-3 py-1 ${!watched ? "border-accent text-accent" : "border-border text-muted"}`}
              >
                {t("scanner.market")}
              </button>
              <button
                onClick={() => setWatched(true)}
                className={`rounded-full border px-3 py-1 ${watched ? "border-accent text-accent" : "border-border text-muted"}`}
              >
                ⭐ {t("scanner.watched")}
              </button>
            </div>
          )}
          <Boards tab={tab} watched={watched && !!user} onPick={setPicked} />
        </>
      )}

      {picked && <ScannerSheet picked={picked} onClose={() => setPicked(null)} />}
    </div>
  );
}
