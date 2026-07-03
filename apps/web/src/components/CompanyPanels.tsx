import { type ReactNode, useState } from "react";
import type { Company, NewsItem } from "../lib/api";
import { type Lang, useLang } from "../lib/i18n";
import { Empty } from "./ui";
import { InfoTip } from "./InfoTip";

const OWN_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const discMonth = (iso: string) => {
  const [y, m] = iso.split("-");
  return `${OWN_MONTHS[Number(m) - 1] ?? "?"} ${y}`;
};

// Plain-language help for the jargon fundamentals, each with a worked example — descriptive only.
const F_HELP: Record<string, string> = {
  market_cap:
    "Total value of all shares: price × shares outstanding. Shown in crore (1 Cr = ৳10 million).",
  pe: "Price-to-Earnings: share price ÷ annual EPS. e.g. price ৳100, EPS ৳5 → P/E 20. Compare within a sector.",
  pe_sector:
    "This stock's P/E ÷ its sector's median P/E. Below 1.0× = cheaper than typical peers; above = pricier.",
  pb: "Price-to-Book: share price ÷ net asset value per share. Below 1.0 = trading under book value. e.g. price ৳100, NAV ৳80 → 1.25.",
  yield:
    "Last year's cash dividend as a % of today's price — your real return. Note: DSE declares dividends as a % of the ৳10 face value, so a '10% dividend' = ৳1 cash; on a ৳40 price that's a 2.5% yield. Bonus shares aren't counted.",
  eps: "Earnings per share: yearly profit ÷ shares outstanding. e.g. ৳1.72 earned per share over the year.",
  eps_growth: "Change in EPS vs the prior year. e.g. -17.3% means earnings per share fell 17.3%.",
  nav: "Net Asset Value per share — the company's book value behind each share. e.g. ৳57 of net assets per share.",
};

const F_HELP_BN: Record<string, string> = {
  market_cap: "সব শেয়ারের মোট মূল্য: দাম × মোট শেয়ার। কোটিতে দেখানো (১ কোটি = ১ কোটি টাকা)।",
  pe: "মূল্য-আয় অনুপাত: শেয়ারের দাম ÷ বার্ষিক EPS। যেমন দাম ৳১০০, EPS ৳৫ → P/E ২০। একই খাতে তুলনা করুন।",
  pe_sector: "এই শেয়ারের P/E ÷ খাতের মধ্যমা P/E। ১.০×-এর নিচে = সাধারণ সমকক্ষদের চেয়ে সস্তা; উপরে = দামি।",
  pb: "মূল্য-বইমূল্য অনুপাত: দাম ÷ শেয়ারপ্রতি নিট সম্পদমূল্য। ১.০-এর নিচে = বইমূল্যের নিচে লেনদেন। যেমন দাম ৳১০০, NAV ৳৮০ → ১.২৫।",
  yield:
    "আজকের দামের শতাংশ হিসেবে গত বছরের নগদ লভ্যাংশ — আপনার আসল রিটার্ন। মনে রাখুন: DSE-তে লভ্যাংশ ঘোষণা হয় ফেস ভ্যালু ৳১০-এর শতাংশে, তাই '১০% লভ্যাংশ' = ৳১ নগদ; ৳৪০ দামে সেটা ২.৫% ইল্ড। বোনাস শেয়ার গণনা হয় না।",
  eps: "শেয়ারপ্রতি আয়: বার্ষিক মুনাফা ÷ মোট শেয়ার। যেমন বছরে শেয়ারপ্রতি ৳১.৭২ আয়।",
  eps_growth: "আগের বছরের তুলনায় EPS পরিবর্তন। যেমন -১৭.৩% মানে শেয়ারপ্রতি আয় ১৭.৩% কমেছে।",
  nav: "শেয়ারপ্রতি নিট সম্পদমূল্য — প্রতি শেয়ারের পেছনে কোম্পানির বইমূল্য। যেমন শেয়ারপ্রতি ৳৫৭ নিট সম্পদ।",
};
const fhelp = (key: string, lang: Lang) =>
  (lang === "bn" ? F_HELP_BN[key] : undefined) ?? F_HELP[key];

const NEWS_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
// "2026-07-07" → "7 Jul"; returns the raw string if it isn't an ISO date.
const shortDate = (iso?: string): string => {
  if (!iso) return "";
  const [, m, d] = iso.split("-");
  if (!d) return iso;
  return `${Number(d)} ${NEWS_MONTHS[Number(m) - 1] ?? "?"}`;
};
// "−৳1.87" / "৳1.50" — explicit minus sign + 2 decimals for per-share figures (distinct from the
// crore-formatting `taka` below used elsewhere in this file).
const takaSigned = (v: number): string => `${v < 0 ? "−" : ""}৳${Math.abs(v).toFixed(2)}`;

const fillT = (t: (k: string) => string, key: string, vars: Record<string, string | number>) =>
  t(key).replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? ""));

// Localised category name, falling back to the raw key if a translation is missing.
const catName = (c: string, t: (k: string) => string): string => {
  const tr = t(`cat.${c}`);
  return tr.startsWith("cat.") ? c : tr;
};

const catDot = (c: string): string => {
  if (c === "dividend") return "bg-up";
  if (c === "halt") return "bg-down";
  if (c === "board_meeting" || c === "corporate_action") return "bg-muted";
  return "bg-accent";
};

// True only when there's a structured card to show — the materiality gate: decoded items become
// rich cards, everything else (bare ratings, board-meeting schedules) collapses to a one-liner.
function hasDecoded(n: NewsItem): boolean {
  const d = n.details;
  if (!d) return false;
  if (n.category === "earnings") return d.eps_current != null;
  if (n.category === "dividend") return d.cash_pct != null || d.stock_pct != null || d.no_dividend === true;
  if (n.category === "corporate_action" || n.category === "halt") return !!(d.record_date || d.spot_from);
  if (n.category === "rating") return !!(d.long_term || d.short_term);
  return false;
}

const isFuture = (iso: string | undefined, today: string): boolean => !!iso && iso >= today;

// The plain-language explainer, now a tap-to-open disclosure instead of a line repeated on every
// card — the education stays, the clutter goes.
function Explainer({ text }: { text: string }) {
  const { t } = useLang();
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 text-[11px] text-muted"
        aria-expanded={open}
      >
        <span aria-hidden>ⓘ</span>
        {t("news.whatItMeans")}
        <span aria-hidden>{open ? "▴" : "▾"}</span>
      </button>
      {open && <p className="mt-1 text-xs text-muted leading-relaxed">{text}</p>}
    </div>
  );
}

function CompactRow({ n }: { n: NewsItem }) {
  const { t } = useLang();
  const d = n.details;
  let desc: string;
  if (n.category === "board_meeting") {
    const bits = (d?.agenda ?? []).map((a) =>
      a === "financials"
        ? fillT(t, "news.board.financials", { period: t(`news.period.${d?.period ?? "annual"}`) })
        : t("news.board.dividend"),
    );
    desc = bits.length ? bits.join(t("news.board.and")) : catName(n.category, t);
  } else {
    desc = n.headline.replace(/^[A-Z0-9.&-]+:\s*/, ""); // drop the "CODE: " prefix
  }
  return (
    <div className="flex items-center gap-2 py-1.5 px-1 text-xs">
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${catDot(n.category)}`} />
      <span className="text-muted shrink-0">{catName(n.category, t)}</span>
      <span className="flex-1 min-w-0 truncate text-text/90">{desc}</span>
      <span className="text-muted shrink-0 tnum">{shortDate(n.published_at)}</span>
    </div>
  );
}

// Forward-looking events pulled from decoded dates — only ever REAL future dates (never inferred),
// so the strip is hidden when nothing is scheduled rather than guessing.
function UpcomingStrip({ items, today }: { items: NewsItem[]; today: string }) {
  const { t } = useLang();
  const events = items
    .map((n) => {
      const d = n.details;
      if (n.category === "board_meeting" && isFuture(d?.meeting_date, today)) {
        const bits = (d?.agenda ?? []).map((a) =>
          a === "financials"
            ? fillT(t, "news.board.financials", { period: t(`news.period.${d?.period ?? "annual"}`) })
            : t("news.board.dividend"),
        );
        return { date: d!.meeting_date!, label: catName("board_meeting", t), sub: bits.join(t("news.board.and")) };
      }
      if ((n.category === "corporate_action" || n.category === "halt") && isFuture(d?.record_date, today))
        return { date: d!.record_date!, label: t("news.recordDate"), sub: "" };
      return null;
    })
    .filter((e): e is { date: string; label: string; sub: string } => e !== null)
    .sort((a, b) => a.date.localeCompare(b.date));
  if (!events.length) return null;
  return (
    <section className="bg-surface border border-accent/40 rounded-2xl p-3">
      <div className="text-[11px] font-semibold text-accent mb-2">{t("news.upcoming")}</div>
      <div className="flex flex-col gap-2">
        {events.map((e, i) => (
          <div key={i} className="flex items-center justify-between gap-2">
            <div className="min-w-0">
              <div className="text-[13px] font-semibold truncate">{e.label}</div>
              {e.sub && <div className="text-[11px] text-muted truncate">{e.sub}</div>}
            </div>
            <div className="text-sm font-semibold text-accent shrink-0 tnum">{shortDate(e.date)}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

// 12-month at-a-glance digest, computed from the feed. Every cell is optional — shown only when the
// data exists (omit over mislead).
// --- Beginner-first news presentation (2026-07 redesign) ------------------------------
// The decoded facts ARE the interface: plain-language headlines, an importance tier per
// item (only Important/Caution take screen space; Routine folds away), countdown chips and
// a fact-aware "what it means". All deterministic from the decoded details — no LLM.

type NewsTier = "caution" | "important" | "routine";

function newsTier(n: NewsItem): NewsTier {
  if (n.category === "halt") return "caution";
  // Dividend/earnings/rating notices earn "Important" ONLY when the decode extracted real
  // substance (a %, an EPS, a grade). An undecoded one — e.g. "dividend by a subsidiary
  // company" — can't be presented helpfully, and a big badge on it is noise pretending to
  // be signal. Those fold into the routine drawer.
  if (["earnings", "dividend", "rating"].includes(n.category))
    return hasDecoded(n) ? "important" : "routine";
  return n.strength >= 60 ? "important" : "routine";
}

// Raw DSE headlines on the symbol's own page: drop the leading "CODE:" (redundant here),
// tame ALL-CAPS shouting, and trim trailing periods/whitespace.
function cleanHeadline(raw: string): string {
  let h = raw.replace(/^[A-Z0-9.&()-]{2,16}\s*[:\-–]\s*/, "").trim();
  const letters = h.replace(/[^A-Za-z]/g, "");
  const uppers = h.replace(/[^A-Z]/g, "");
  if (letters.length > 8 && uppers.length / letters.length > 0.7) {
    // Title-case the shouting, keeping connective words small: "Q3 Financial Statements
    // of Olympic Industries Limited" rather than all-lowercase soup.
    const small = new Set(["of", "the", "by", "a", "an", "and", "for", "to", "in", "on", "at"]);
    h = h
      .toLowerCase()
      .split(/\s+/)
      .map((w, i) =>
        i > 0 && small.has(w) ? w : w.charAt(0).toUpperCase() + w.slice(1),
      )
      .join(" ");
  }
  return h.replace(/\.\s*$/, "");
}

const dhakaTodayIso = () => new Date(Date.now() + 6 * 3600_000).toISOString().slice(0, 10);
const daysUntil = (iso?: string): number | null =>
  iso ? Math.round((Date.parse(iso) - Date.parse(dhakaTodayIso())) / 86_400_000) : null;

const PERIOD_EN = { Q1: "in Q1", H1: "in H1", Q3: "in Q3", annual: "for the year" } as const;
const PERIOD_BN = { Q1: "১ম প্রান্তিকে", H1: "অর্ধবার্ষিকে", Q3: "৩য় প্রান্তিকে", annual: "পুরো বছরে" } as const;

// The sentence a person would actually say — built from the decoded numbers; null → raw headline.
function plainHeadline(n: NewsItem, bn: boolean): string | null {
  const d = n.details;
  if (!d) return null;
  if (n.category === "earnings" && d.eps_current != null) {
    const p = d.period ? (bn ? PERIOD_BN[d.period] : PERIOD_EN[d.period]) : bn ? "এই প্রান্তিকে" : "this period";
    let head = bn
      ? `শেয়ারপ্রতি আয় ${p} ${takaSigned(d.eps_current)}`
      : `Earned ${takaSigned(d.eps_current)} per share ${p}`;
    if (d.eps_prior != null && d.eps_prior > 0) {
      const delta = ((d.eps_current - d.eps_prior) / d.eps_prior) * 100;
      head += bn
        ? ` — আগের বছরের চেয়ে ${delta >= 0 ? "+" : ""}${delta.toFixed(0)}%`
        : ` — ${delta >= 0 ? "up" : "down"} ${Math.abs(delta).toFixed(0)}% from last year`;
    } else if (d.eps_current < 0) {
      head += bn ? " (লোকসান)" : " (a loss)";
    }
    return head;
  }
  if (n.category === "dividend") {
    if (d.no_dividend) return bn ? "এ বছর কোনো লভ্যাংশ ঘোষণা হয়নি" : "No dividend declared this year";
    const parts: string[] = [];
    if (d.cash_pct != null) parts.push(bn ? `${d.cash_pct}% নগদ` : `${d.cash_pct}% cash`);
    if (d.stock_pct != null) parts.push(bn ? `${d.stock_pct}% স্টক` : `${d.stock_pct}% stock`);
    if (!parts.length) return null;
    let head = bn ? `${parts.join(" + ")} লভ্যাংশ ঘোষণা` : `${parts.join(" + ")} dividend declared`;
    if (d.per_share_cash != null)
      head += bn ? ` — শেয়ারপ্রতি ৳${d.per_share_cash}` : ` — ৳${d.per_share_cash} per share`;
    return head;
  }
  if (n.category === "rating" && (d.long_term || d.short_term)) {
    const parts: string[] = [];
    if (d.long_term) parts.push(`${d.long_term} (${bn ? "দীর্ঘমেয়াদি" : "long-term"})`);
    if (d.short_term) parts.push(`${d.short_term} (${bn ? "স্বল্পমেয়াদি" : "short-term"})`);
    return (bn ? "ক্রেডিট রেটিং: " : "Credit rating: ") + parts.join(", ");
  }
  return null;
}

// The fact-aware "মানে কী" — references the actual numbers, teaches without advising.
function whatItMeans(n: NewsItem, bn: boolean): string | null {
  const d = n.details;
  // No decode = we don't actually know what this notice says; a generic per-category
  // explainer could teach the WRONG thing (e.g. a subsidiary's dividend has no record
  // date for THIS stock's holders). Halts are the exception — the meaning is structural.
  if (n.category !== "halt" && !hasDecoded(n)) return null;
  if (n.category === "earnings" && d?.eps_current != null) {
    const rising = d.eps_prior != null && d.eps_current > d.eps_prior;
    if (bn)
      return rising
        ? "কোম্পানি গত বছরের একই সময়ের চেয়ে শেয়ারপ্রতি বেশি মুনাফা করেছে। ক্রমবর্ধমান EPS-ই দীর্ঘমেয়াদে দামকে সমর্থন করে — তবে এক প্রান্তিক একটি তথ্যবিন্দু, রায় নয়।"
        : "শেয়ারপ্রতি আয় আগের বছরের চেয়ে কমেছে। কারণটি (খাত-ব্যাপী নাকি কোম্পানির নিজস্ব) যাচাই করা জরুরি — এক প্রান্তিক দিয়ে সিদ্ধান্ত নয়।";
    return rising
      ? "The company made more profit per share than the same period last year. Rising EPS is what supports a share price over time — but one period is a data point, not a verdict."
      : "Profit per share fell versus last year. Worth checking whether the cause is sector-wide or company-specific — one period is never the whole story.";
  }
  if (n.category === "dividend") {
    if (d?.no_dividend)
      return bn
        ? "লভ্যাংশ না দেওয়ার অনেক কারণ থাকতে পারে — মুনাফা কম, নাকি টাকা ব্যবসায় পুনর্বিনিয়োগ? আর্থিক বিবরণী দেখুন।"
        : "No dividend can mean weak profit or profits reinvested in the business — the financials tell you which. Worth checking.";
    // The most misread number on the DSE: the declared % is of the ৳10 face value,
    // never of the market price. Decode it with this filing's own numbers.
    const per100 = d?.per_share_cash != null ? +(d.per_share_cash * 100).toFixed(2) : null;
    const conv =
      d?.cash_pct != null
        ? bn
          ? `"${d.cash_pct}%" মানে ফেস ভ্যালু ৳১০-এর ${d.cash_pct}%${d.per_share_cash != null ? ` = শেয়ারপ্রতি ৳${d.per_share_cash}। অর্থাৎ ১০০ শেয়ার থাকলে পাবেন ৳${per100}` : ""} — আজকের বাজারদরের ${d.cash_pct}% নয়। `
          : `The "${d.cash_pct}%" means ${d.cash_pct}% of the ৳10 face value${d.per_share_cash != null ? ` = ৳${d.per_share_cash} per share. So if you hold 100 shares, you receive ৳${per100}` : ""} — it is NOT ${d.cash_pct}% of today's market price. `
        : "";
    return (
      conv +
      (bn
        ? "রেকর্ড ডেটে শেয়ারটি আপনার BO-তে থাকলে লভ্যাংশ পাবেন। রেকর্ড ডেটের পর দাম সাধারণত লভ্যাংশের পরিমাণে সমন্বয় হয় — এটি ক্ষতি নয়, হিসাব।"
        : "Own the share in your BO account on the record date to receive it. After the record date the price usually adjusts by roughly the dividend amount — that's arithmetic, not a loss.")
    );
  }
  if (n.category === "rating")
    return bn
      ? "রেটিং কোম্পানির ঋণ শোধের সক্ষমতার মূল্যায়ন — শেয়ারের দাম কোথায় যাবে তার পূর্বাভাস নয়।"
      : "A credit rating assesses the company's ability to repay debt — it is not a forecast of where the share price goes.";
  if (n.category === "halt")
    return bn
      ? "মূল্য-সংবেদনশীল খবরের আগে লেনদেন সাময়িক বন্ধ রাখা হয় যাতে সবাই একসাথে খবরটি পায়। খবরটি কী ছিল, সেটাই আসল প্রশ্ন।"
      : "Trading pauses so everyone receives price-sensitive news at the same time. The real question is what that news was.";
  return null;
}

const TIER_ICON: Record<string, string> = {
  earnings: "📊",
  dividend: "💵",
  rating: "🏷️",
  halt: "⚠️",
  corporate_action: "📋",
  board_meeting: "🗓️",
};

function FactChips({ n, ltp, bn }: { n: NewsItem; ltp?: number | null; bn: boolean }) {
  const d = n.details;
  if (!d) return null;
  const chips: { text: string; tone?: "up" | "down" | "accent" }[] = [];
  if (n.category === "earnings" && d.eps_current != null) {
    if (d.eps_prior != null && d.eps_prior > 0) {
      const delta = ((d.eps_current - d.eps_prior) / d.eps_prior) * 100;
      chips.push({
        text: `EPS ${takaSigned(d.eps_current)} ${delta >= 0 ? "▲" : "▼"} ${Math.abs(delta).toFixed(0)}%`,
        tone: delta >= 0 ? "up" : "down",
      });
      chips.push({ text: bn ? `আগের বছর ${takaSigned(d.eps_prior)}` : `last year ${takaSigned(d.eps_prior)}` });
    } else {
      chips.push({ text: `EPS ${takaSigned(d.eps_current)}`, tone: d.eps_current >= 0 ? "up" : "down" });
    }
    if (d.nav != null) chips.push({ text: `NAV ${takaSigned(d.nav)}` });
  }
  if (n.category === "dividend") {
    // The realest possible number first: what 100 shares actually pays. This is what
    // finally breaks the "10% dividend = 10% return" illusion for a new investor.
    if (d.per_share_cash != null) {
      const cash100 = +(d.per_share_cash * 100).toFixed(2);
      chips.push({
        text: bn
          ? `১০০ শেয়ার থাকলে পাবেন ৳${cash100} (কর কাটার আগে)`
          : `100 shares → ৳${cash100} cash (before tax)`,
        tone: "up",
      });
      if (ltp) {
        const y = ((d.per_share_cash / ltp) * 100).toFixed(1);
        chips.push({
          text: bn ? `আজকের দাম ৳${ltp}-এ রিটার্ন ~${y}%` : `~${y}% of today's ৳${ltp} price`,
        });
      }
    }
    const days = daysUntil(d.record_date);
    if (d.record_date)
      chips.push({
        text:
          `${bn ? "রেকর্ড ডেট" : "record date"} ${shortDate(d.record_date)}` +
          (days != null && days >= 0 ? (bn ? ` · ${days} দিন বাকি` : ` · in ${days} days`) : ""),
        tone: "accent",
      });
    if (d.agm_date) chips.push({ text: `AGM ${shortDate(d.agm_date)}` });
  }
  if (n.category === "rating" && d.outlook) chips.push({ text: `${bn ? "আউটলুক" : "outlook"}: ${d.outlook}` });
  if (!chips.length) return null;
  const toneCls = (t?: string) =>
    t === "up"
      ? "text-up bg-up/10 border border-up/30"
      : t === "down"
        ? "text-down bg-down/10 border border-down/30"
        : t === "accent"
          ? "text-accent bg-accent/10 border border-accent/30"
          : "text-muted bg-card";
  return (
    <div className="mt-2.5 flex flex-wrap gap-1.5">
      {chips.map((c, i) => (
        <span key={i} className={`rounded-lg px-2 py-1 text-[11px] font-semibold tnum ${toneCls(c.tone)}`}>
          {c.text}
        </span>
      ))}
    </div>
  );
}

function ImportantCard({ n, ltp }: { n: NewsItem; ltp?: number | null }) {
  const { t, lang } = useLang();
  const bn = lang === "bn";
  const tier = newsTier(n);
  const plain = plainHeadline(n, bn);
  const meaning = whatItMeans(n, bn);
  const border =
    tier === "caution"
      ? "border-down/40"
      : n.category === "earnings" && (n.details?.eps_prior ?? 0) < (n.details?.eps_current ?? 0)
        ? "border-up/30"
        : "border-border";
  return (
    <div className={`bg-surface border rounded-2xl p-3.5 ${border}`}>
      <div className="flex items-start gap-2.5">
        <span className="text-lg leading-none pt-0.5" aria-hidden>
          {TIER_ICON[n.category] ?? "📰"}
        </span>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 text-[10px]">
            {tier === "caution" ? (
              <span className="font-semibold rounded-full px-2 py-0.5 text-down bg-down/10">
                {bn ? "সতর্কতা" : "Caution"} · {catName(n.category, t)}
              </span>
            ) : (
              <span className="font-semibold rounded-full px-2 py-0.5 text-accent bg-accent/10">
                {bn ? "গুরুত্বপূর্ণ" : "Important"} · {catName(n.category, t)}
              </span>
            )}
            <span className="text-muted tnum">{shortDate(n.published_at)}</span>
          </div>
          <p lang={lang} className="text-sm font-semibold mt-1.5 leading-snug">
            {plain ?? cleanHeadline(n.headline)}
          </p>
          {plain && (
            <p className="text-[10px] text-muted mt-0.5 truncate" title={n.headline}>
              {bn ? "উৎস: DSE ঘোষণা" : "Source: DSE filing"} — {cleanHeadline(n.headline)}
            </p>
          )}
        </div>
      </div>
      <FactChips n={n} ltp={ltp} bn={bn} />
      {meaning && <Explainer text={meaning} />}
    </div>
  );
}

export function NewsPanel({ items, ltp }: { items: NewsItem[]; ltp?: number | null }) {
  const { t, lang } = useLang();
  const bn = lang === "bn";
  const [showRoutine, setShowRoutine] = useState(false);
  if (!items.length) return <Empty>{t("news.empty")}</Empty>;
  const today = dhakaTodayIso();

  const upcomingMeeting = (n: NewsItem): boolean =>
    (n.category === "board_meeting" && isFuture(n.details?.meeting_date, today)) ||
    ((n.category === "corporate_action" || n.category === "halt") &&
      isFuture(n.details?.record_date, today));

  const past = items.filter((n) => !upcomingMeeting(n));
  const important = past.filter((n) => newsTier(n) !== "routine");
  const routine = past.filter((n) => newsTier(n) === "routine");

  const weekAgo = new Date(Date.parse(today) - 7 * 86_400_000).toISOString().slice(0, 10);
  const thisWeek = important.filter((n) => n.published_at >= weekAgo);
  const earlier = important.filter((n) => n.published_at < weekAgo);

  const sectionLabel = (text: string) => (
    <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted px-1">{text}</div>
  );

  return (
    <div className="flex flex-col gap-2.5">
      <UpcomingStrip items={items} today={today} />

      {important.length === 0 && (
        <Empty>{bn ? "সাম্প্রতিক গুরুত্বপূর্ণ কোনো খবর নেই — এটাও তথ্য।" : "No important news recently — that's information too."}</Empty>
      )}

      {thisWeek.length > 0 && sectionLabel(bn ? "এই সপ্তাহ" : "This week")}
      {thisWeek.map((n, i) => (
        <ImportantCard key={`w${i}`} n={n} ltp={ltp} />
      ))}

      {earlier.length > 0 && sectionLabel(bn ? "আগে" : "Earlier")}
      {earlier.map((n, i) => (
        <ImportantCard key={`e${i}`} n={n} ltp={ltp} />
      ))}

      {routine.length > 0 && (
        <div className="rounded-2xl border border-dashed border-border px-3.5 py-2.5">
          <button
            onClick={() => setShowRoutine((v) => !v)}
            className="flex w-full items-center gap-2 text-left"
          >
            <span aria-hidden>🗂️</span>
            <span className="text-xs text-muted">
              {routine.length} {bn ? "টি রুটিন নোটিশ — বোর্ড সূচি, স্পট খবর" : "routine notices — board schedules, spot news"}
            </span>
            <span className="ml-auto text-[11px] font-semibold text-accent">
              {showRoutine ? (bn ? "লুকান" : "Hide") : bn ? "দেখুন" : "Show"}
            </span>
          </button>
          {showRoutine && (
            <div className="mt-2 flex flex-col gap-1.5 border-t border-border/60 pt-2">
              {routine.map((n, i) => (
                <CompactRow key={i} n={n} />
              ))}
            </div>
          )}
        </div>
      )}

      <p className="text-[10px] text-muted">{t("news.footer")}</p>
    </div>
  );
}

const dash = "—";
const pct = (n: number | null) => (n == null ? dash : `${n.toFixed(2)}%`);
const ratio = (n: number | null) => (n == null ? dash : n.toFixed(2));
const taka = (n: number | null) =>
  n == null ? dash : `৳${n.toLocaleString()}`;
// DSE thinks in crore (1 cr = 10 million)
const crore = (mn: number | null) =>
  mn == null
    ? dash
    : `৳${(mn / 10).toLocaleString(undefined, { maximumFractionDigits: 0 })} Cr`;

function Row({
  label,
  value,
  hint,
  help,
}: {
  label: string;
  value: string;
  hint?: string;
  help?: string;
}) {
  return (
    <div className="flex items-baseline justify-between py-2 border-b border-border/60 last:border-0">
      <span className="flex items-center gap-1.5 text-xs text-muted">
        {label}
        {help && <InfoTip text={help} />}
      </span>
      <span className="text-sm font-semibold tnum">
        {value}
        {hint && <span className="text-muted font-normal"> {hint}</span>}
      </span>
    </div>
  );
}

function Card({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <div className="font-semibold text-sm mb-1">{title}</div>
      {children}
    </div>
  );
}

export function FundamentalsPanel({ f }: { f: Company["fundamentals"] }) {
  const { t, lang } = useLang();
  const yoy =
    f.eps_growth_yoy == null
      ? dash
      : `${f.eps_growth_yoy > 0 ? "+" : ""}${f.eps_growth_yoy.toFixed(1)}%`;
  return (
    <Card title={t("tab.fundamentals")}>
      <Row label={t("f.marketCap")} value={crore(f.market_cap_mn)} help={fhelp("market_cap", lang)} />
      <Row label={t("f.pe")} value={ratio(f.pe_ratio)} help={fhelp("pe", lang)} />
      <Row
        label={t("f.peSector")}
        value={f.pe_vs_sector == null ? dash : `${f.pe_vs_sector.toFixed(2)}×`}
        help={fhelp("pe_sector", lang)}
      />
      <Row label={t("f.pb")} value={ratio(f.pb_ratio)} help={fhelp("pb", lang)} />
      <Row label={t("f.divYield")} value={pct(f.dividend_yield)} help={fhelp("yield", lang)} />
      <Row label={t("f.epsAnnual")} value={taka(f.eps)} help={fhelp("eps", lang)} />
      <Row label={t("f.epsGrowthYoY")} value={yoy} help={fhelp("eps_growth", lang)} />
      <Row label={t("f.navShare")} value={taka(f.nav_per_share)} help={fhelp("nav", lang)} />
      <Row
        label={t("range.52w")}
        value={`${taka(f.week52_low)} – ${taka(f.week52_high)}`}
      />
      <Row label={t("f.freeFloatCap")} value={crore(f.free_float_cap_mn)} />
      <Row
        label={t("f.sharesOut")}
        value={
          f.outstanding_shares == null
            ? dash
            : f.outstanding_shares.toLocaleString()
        }
      />
      <Row label={t("f.faceValue")} value={taka(f.face_value)} />
      <Row label={t("f.sector")} value={f.sector ?? dash} />
      <Row label={t("f.creditRating")} value={f.credit_rating ?? dash} />
      <p className="text-[10px] text-muted mt-2">
        Valuation derived from the latest close. Descriptive, not advice.
      </p>
    </Card>
  );
}

// Plain-language read of who's been buying/selling, from the month-over-month deltas.
function smartMoneyRead(o: Company["ownership"]): string {
  const moves: string[] = [];
  if (o.institute_delta != null && o.institute_delta >= 0.1) moves.push("institutions added");
  else if (o.institute_delta != null && o.institute_delta <= -0.1) moves.push("institutions trimmed");
  if (o.foreign_delta != null && o.foreign_delta >= 0.1) moves.push("foreign investors added");
  else if (o.foreign_delta != null && o.foreign_delta <= -0.1) moves.push("foreign investors trimmed");
  if (!moves.length) return "Big-money holdings barely changed since the prior disclosure.";
  const s = moves.join(", and ") + " since the prior disclosure.";
  return s.charAt(0).toUpperCase() + s.slice(1);
}

const OWN_GREEN = "#2fbf71";

// Who each holder group actually is — the labels are meaningless to a first-time investor.
const OWN_WHO: Record<string, string> = {
  sponsor:
    "The company's founders, directors and their families — the insiders. A large stake means their own money sits next to yours; a steady fall is worth reading into.",
  institute:
    "Banks, mutual funds, insurers and other professional investors. They research before they buy, so changes here are watched closely.",
  foreign:
    "Overseas funds investing in the DSE — often the most selective money in the market.",
  public: "Everyone else — ordinary retail investors like most people using this app.",
};

export function OwnershipPanel({ o }: { o: Company["ownership"] }) {
  const cats = [
    { key: "sponsor", label: "Sponsor / Director", color: "var(--color-accent)", v: o.sponsor_pct },
    { key: "institute", label: "Institutional", color: "#0ea5e9", v: o.institute_pct },
    { key: "foreign", label: "Foreign", color: OWN_GREEN, v: o.foreign_pct },
    { key: "public", label: "Public", color: "var(--color-muted)", v: o.public_pct },
  ] as const;
  if (!cats.some((c) => c.v != null)) return <Empty>No ownership disclosure yet.</Empty>;

  const hist = o.history ?? [];
  const first = hist[0];
  const freeFloat = (o.institute_pct ?? 0) + (o.foreign_pct ?? 0) + (o.public_pct ?? 0);
  const stale =
    o.as_of != null && (Date.now() - new Date(o.as_of).getTime()) / 86_400_000 > 270;

  // Smart money = institutions + foreign. The positive story to highlight: has it grown over the
  // disclosed window? (first → latest). Only celebrate a real rise; otherwise stay factual.
  const smartNow = (o.institute_pct ?? 0) + (o.foreign_pct ?? 0);
  const smartThen = first ? (first.institute ?? 0) + (first.foreign ?? 0) : null;
  const smartGrew = !stale && smartThen != null && smartNow - smartThen >= 0.5;
  // Latest step of the same combined series — surfaced as a caveat when it disagrees with
  // the long-run rise, so the banner never contradicts the ▼ chips right below it.
  const smartStep =
    hist.length >= 2
      ? (hist[hist.length - 1].institute ?? 0) +
        (hist[hist.length - 1].foreign ?? 0) -
        ((hist[hist.length - 2].institute ?? 0) + (hist[hist.length - 2].foreign ?? 0))
      : null;

  // Sponsor falling streak — same rule as the backend agent (≥3 consecutive declining
  // disclosures, ≥1.0pp cumulative). Insiders steadily reducing is the one ownership story
  // worth a warning banner; a single noisy month is not.
  const sponsorSeries = hist
    .map((p) => p.sponsor)
    .filter((x): x is number => x != null);
  let sponsorRun = 0;
  for (let i = sponsorSeries.length - 1; i > 0; i--) {
    if (sponsorSeries[i] < sponsorSeries[i - 1]) sponsorRun++;
    else break;
  }
  const sponsorDrop =
    sponsorRun >= 3
      ? sponsorSeries[sponsorSeries.length - 1 - sponsorRun] - sponsorSeries[sponsorSeries.length - 1]
      : 0;
  const sponsorStreak = !stale && sponsorRun >= 3 && sponsorDrop >= 1.0;

  const stepDelta = (key: (typeof cats)[number]["key"]) => {
    const s = hist.map((p) => p[key]).filter((x): x is number => x != null);
    return s.length >= 2 ? s[s.length - 1] - s[s.length - 2] : null;
  };
  const chip = (d: number | null) =>
    d == null || Math.abs(d) < 0.01 ? null : (
      <span className={`text-[11px] font-semibold tnum ${d > 0 ? "text-up" : "text-down"}`}>
        {d > 0 ? "▲" : "▼"} {Math.abs(d).toFixed(2)}pp
      </span>
    );

  return (
    <Card title="Ownership">
      {/* Highlight: stale flag, or the positive smart-money story, or a neutral read. */}
      {stale ? (
        <div className="rounded-xl bg-card border border-border p-3 mb-3 text-[13px] leading-snug text-muted">
          ⏳ Latest disclosure {o.as_of ? discMonth(o.as_of) : dash} — DSE hasn't filed a newer one
          for this stock, so the figures below may be out of date.
        </div>
      ) : sponsorStreak ? (
        <div
          className="rounded-xl p-3 mb-3"
          style={{ backgroundColor: "rgba(240,86,74,0.08)", border: "1px solid rgba(240,86,74,0.35)" }}
        >
          <div className="text-[13px] leading-snug font-semibold text-down">
            ⚠️ Sponsor stake falling {sponsorRun} disclosures straight
          </div>
          <div className="text-[12px] text-muted mt-0.5">
            {(sponsorSeries[sponsorSeries.length - 1 - sponsorRun]).toFixed(1)}% →{" "}
            <b className="text-fg">{sponsorSeries[sponsorSeries.length - 1].toFixed(1)}%</b>{" "}
            (−{sponsorDrop.toFixed(1)}pp) — insiders reducing their own stake. Source: DSE
            shareholding disclosures. Descriptive, not advice.
          </div>
        </div>
      ) : smartGrew && smartThen != null && first ? (
        <div
          className="rounded-xl p-3 mb-3"
          style={{ backgroundColor: "rgba(22,199,132,0.10)", border: "1px solid rgba(22,199,132,0.35)" }}
        >
          <div className="text-[13px] leading-snug font-semibold text-up">
            🏦 Big investors hold more than before
          </div>
          <div className="text-[12px] text-muted mt-0.5">
            Institutions + foreign investors hold <b className="text-fg">{smartNow.toFixed(1)}%</b>,
            up from {smartThen.toFixed(1)}% in {discMonth(first.as_of)}
            {smartStep != null && smartStep <= -0.1
              ? ` — though the latest disclosure shows a small dip (−${Math.abs(smartStep).toFixed(2)}pp).`
              : "."}
          </div>
        </div>
      ) : (
        <div className="rounded-xl bg-card border border-border p-3 mb-3 text-[13px] leading-snug">
          🏦 {smartMoneyRead(o)}
        </div>
      )}

      {/* Composition over time — one stacked bar per disclosure, oldest → newest. */}
      <div className="text-[10px] uppercase tracking-wide text-muted/70 mb-1.5">Ownership over time</div>
      <div className="flex flex-col gap-1.5 mb-3">
        {hist.map((p) => (
          <div key={p.as_of} className="flex items-center gap-2">
            <span className="text-[10px] text-muted tnum w-14 shrink-0">{discMonth(p.as_of)}</span>
            <span className="flex h-2.5 flex-1 rounded-full overflow-hidden bg-border/40">
              {cats.map((c) => (
                <span key={c.key} style={{ width: `${p[c.key] ?? 0}%`, backgroundColor: c.color }} />
              ))}
            </span>
          </div>
        ))}
      </div>

      {/* Legend + latest % + change vs prior disclosure. */}
      {cats.map((c) => (
        <div key={c.key} className="flex items-center gap-3 py-2 border-b border-border/60">
          <span className="flex items-center gap-2 flex-1 min-w-0">
            <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: c.color }} />
            <span className="text-xs text-muted truncate">{c.label}</span>
            <InfoTip text={OWN_WHO[c.key]} />
          </span>
          {chip(stepDelta(c.key))}
          <span className="text-sm font-semibold tnum w-16 text-right">{pct(c.v)}</span>
        </div>
      ))}

      <p className="text-[10px] text-muted mt-2">
        Free float ~{freeFloat.toFixed(0)}%.{" "}
        {hist.length > 1 ? `${hist.length} disclosures, ${discMonth(hist[0].as_of)}–${discMonth(o.as_of ?? hist[hist.length - 1].as_of)}. ` : ""}
        ▲▼ = change vs the prior disclosure, in percentage points (0.65pp = the group&apos;s
        share of the company moved by 0.65). Descriptive, not advice.
      </p>
    </Card>
  );
}

// One compact key-stat box.
function Stat({ label, value, tip }: { label: string; value: ReactNode; tip?: string }) {
  return (
    <div className="flex-1 rounded-lg bg-card border border-border p-2 min-w-0">
      <div className="text-[10px] text-muted flex items-center gap-1">
        {label}
        {tip && <InfoTip text={tip} />}
      </div>
      <div className="text-sm font-semibold tnum mt-0.5 truncate">{value}</div>
    </div>
  );
}

// Mini year-by-year bar chart: value above each bar, year below; latest highlighted, losses in red.
function YearBars({
  data,
  fmt,
  color = "var(--color-accent)",
}: {
  data: { year: number; v: number | null }[];
  fmt: (n: number) => string;
  color?: string;
}) {
  const pts = data.filter((d): d is { year: number; v: number } => d.v != null);
  if (pts.length < 2) return null;
  const max = Math.max(...pts.map((d) => Math.abs(d.v)), 0.0001);
  return (
    <div className="flex items-end gap-1.5 mt-2 mb-3">
      {pts.map((d, i) => {
        const last = i === pts.length - 1;
        const bg = d.v < 0 ? "var(--color-down)" : last ? color : "var(--color-border)";
        return (
          <div key={d.year} className="flex-1 flex flex-col items-center min-w-0">
            <span className="text-[9px] text-muted tnum mb-0.5">{fmt(d.v)}</span>
            <div className="w-full h-14 flex items-end">
              <div
                className="w-full rounded-t"
                style={{ height: `${Math.max(4, (Math.abs(d.v) / max) * 100)}%`, backgroundColor: bg }}
              />
            </div>
            <span className={`text-[9px] tnum mt-1 ${last ? "text-fg font-semibold" : "text-muted"}`}>
              &rsquo;{String(d.year).slice(2)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

const _EY_TIP =
  "Earnings yield = a company's yearly EPS ÷ its share price (the inverse of P/E). e.g. 5% means it earns ৳5 a year for every ৳100 you pay. Higher = more earnings for your money. Compare it with the bank deposit rate.";
const _PAYOUT_TIP =
  "Payout ratio = cash dividend ÷ EPS — how much of each year's profit is handed out as cash. e.g. 45% means ৳45 of every ৳100 earned is paid out; the rest is kept in the business.";

export function EarningsPanel({
  earnings,
  dividends,
  f,
}: {
  earnings: Company["earnings"];
  dividends: Company["dividends"];
  f: Company["fundamentals"];
}) {
  if (!earnings.length && !dividends.length)
    return <Empty>No earnings history yet.</Empty>;

  const yoy = f.eps_growth_yoy;
  const yoyChip =
    yoy == null ? null : (
      <span className={`text-[11px] ${yoy >= 0 ? "text-up" : "text-down"}`}>
        {" "}
        {yoy >= 0 ? "▲" : "▼"}
        {Math.abs(yoy).toFixed(0)}%
      </span>
    );
  const earningsYield = f.pe_ratio && f.pe_ratio > 0 ? 100 / f.pe_ratio : null;

  const eps0 = f.eps ?? earnings[0]?.eps ?? null;
  const face = f.face_value ?? 10;
  const latestCash = dividends[0]?.cash_pct ?? null;
  const payout =
    latestCash != null && eps0 ? ((latestCash / 100) * face) / eps0 * 100 : null;

  const epsBars = earnings.slice(0, 6).reverse().map((e) => ({ year: e.fiscal_year, v: e.eps }));
  const cashBars = dividends.slice(0, 6).reverse().map((d) => ({ year: d.year, v: d.cash_pct }));

  return (
    <div className="flex flex-col gap-3">
      {earnings.length > 0 && (
        <Card title="Earnings">
          <div className="flex gap-2 mb-1">
            <Stat label="EPS (latest)" value={<>{taka(earnings[0]?.eps ?? null)}{yoyChip}</>} />
            <Stat label="Earnings yield" value={pct(earningsYield)} tip={_EY_TIP} />
            <Stat label="NAV / share" value={taka(earnings[0]?.nav_per_share ?? null)} />
          </div>
          <YearBars data={epsBars} fmt={(n) => `৳${n.toFixed(1)}`} />
          <div className="grid grid-cols-4 text-[11px] text-muted font-semibold pb-1 border-b border-border">
            <span>FY</span>
            <span className="text-right">EPS</span>
            <span className="text-right">NAV</span>
            <span className="text-right">Profit</span>
          </div>
          {earnings.slice(0, 6).map((e) => (
            <div
              key={e.fiscal_year}
              className="grid grid-cols-4 text-sm tnum py-1.5 border-b border-border/60 last:border-0"
            >
              <span>{e.fiscal_year}</span>
              <span className="text-right">{taka(e.eps)}</span>
              <span className="text-right">{taka(e.nav_per_share)}</span>
              <span className="text-right text-muted">{crore(e.profit_mn)}</span>
            </div>
          ))}
        </Card>
      )}
      {dividends.length > 0 && (
        <Card title="Dividends">
          <div className="flex gap-2 mb-1">
            <Stat label="Dividend yield" value={pct(f.dividend_yield)} />
            <Stat label="Cash (latest)" value={pct(latestCash)} />
            <Stat label="Payout ratio" value={pct(payout)} tip={_PAYOUT_TIP} />
          </div>
          <YearBars data={cashBars} fmt={(n) => `${n.toFixed(0)}%`} color="#0ea5e9" />
          <div className="grid grid-cols-3 text-[11px] text-muted font-semibold pb-1 border-b border-border">
            <span>Year</span>
            <span className="text-right">Cash</span>
            <span className="text-right">Bonus</span>
          </div>
          {dividends.slice(0, 6).map((d) => (
            <div
              key={d.year}
              className="grid grid-cols-3 text-sm tnum py-1.5 border-b border-border/60 last:border-0"
            >
              <span>{d.year}</span>
              <span className="text-right">{pct(d.cash_pct)}</span>
              <span className="text-right">{pct(d.bonus_pct)}</span>
            </div>
          ))}
        </Card>
      )}
    </div>
  );
}
