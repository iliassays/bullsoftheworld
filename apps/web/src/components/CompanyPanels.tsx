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
    "Last year's cash dividend as a % of today's price. e.g. ৳1 cash on a ৳20 price = 5%. Bonus shares aren't counted.",
  eps: "Earnings per share: yearly profit ÷ shares outstanding. e.g. ৳1.72 earned per share over the year.",
  eps_growth: "Change in EPS vs the prior year. e.g. -17.3% means earnings per share fell 17.3%.",
  nav: "Net Asset Value per share — the company's book value behind each share. e.g. ৳57 of net assets per share.",
};

const F_HELP_BN: Record<string, string> = {
  market_cap: "সব শেয়ারের মোট মূল্য: দাম × মোট শেয়ার। কোটিতে দেখানো (১ কোটি = ১ কোটি টাকা)।",
  pe: "মূল্য-আয় অনুপাত: শেয়ারের দাম ÷ বার্ষিক EPS। যেমন দাম ৳১০০, EPS ৳৫ → P/E ২০। একই খাতে তুলনা করুন।",
  pe_sector: "এই শেয়ারের P/E ÷ খাতের মধ্যমা P/E। ১.০×-এর নিচে = সাধারণ সমকক্ষদের চেয়ে সস্তা; উপরে = দামি।",
  pb: "মূল্য-বইমূল্য অনুপাত: দাম ÷ শেয়ারপ্রতি নিট সম্পদমূল্য। ১.০-এর নিচে = বইমূল্যের নিচে লেনদেন। যেমন দাম ৳১০০, NAV ৳৮০ → ১.২৫।",
  yield: "আজকের দামের শতাংশ হিসেবে গত বছরের নগদ লভ্যাংশ। যেমন ৳২০ দামে ৳১ নগদ = ৫%। বোনাস শেয়ার গণনা হয় না।",
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

// One labelled date in the corporate-action timeline.
function DateCell({ label, value, accent }: { label: string; value?: string; accent?: boolean }) {
  if (!value) return null;
  return (
    <div className="flex-1 text-center px-1 py-1.5">
      <div className="text-[10px] text-muted">{label}</div>
      <div className={`text-xs font-semibold ${accent ? "text-accent" : ""}`}>{value}</div>
    </div>
  );
}

const fillT = (t: (k: string) => string, key: string, vars: Record<string, string | number>) =>
  t(key).replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? ""));

// Localised category name, falling back to the raw key if a translation is missing.
const catName = (c: string, t: (k: string) => string): string => {
  const tr = t(`cat.${c}`);
  return tr.startsWith("cat.") ? c : tr;
};

// Category → chip/dot colour, so the eye can triage the feed. Dividends read as money (up/green),
// halts as danger (down/red), routine meetings/actions as neutral, the rest as accent.
const catChip = (c: string): string => {
  if (c === "dividend") return "text-up bg-up/10";
  if (c === "halt") return "text-down bg-down/10";
  if (c === "board_meeting" || c === "corporate_action") return "text-muted bg-border/40";
  return "text-accent bg-accent/10";
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

// Renders the decoded body for one announcement, switching on category. Falls back to nothing
// (the headline alone) when there's no structured detail — so it never shows half-parsed noise.
function DecodedBody({ n }: { n: NewsItem }) {
  const { t } = useLang();
  const d = n.details;
  const fill = (key: string, vars: Record<string, string | number>) => fillT(t, key, vars);
  if (!d) return null;

  if (n.category === "earnings" && d.eps_current != null) {
    const loss = d.eps_current < 0;
    return (
      <div className="mt-2">
        <div className="flex gap-2 flex-wrap">
          <div className="flex-1 min-w-[120px] bg-bg/40 rounded-xl px-3 py-2">
            <div className="text-[11px] text-muted">{t("news.eps")}</div>
            <div className={`text-xl font-bold ${loss ? "text-down" : "text-up"}`}>{takaSigned(d.eps_current)}</div>
            {d.eps_prior != null && (
              <div className="text-[11px] text-muted">{fill("news.epsVsPrior", { prior: takaSigned(d.eps_prior) })}</div>
            )}
          </div>
          {d.nav != null && (
            <div className="flex-1 min-w-[120px] bg-bg/40 rounded-xl px-3 py-2">
              <div className="text-[11px] text-muted">{t("news.nav")}</div>
              <div className="text-xl font-bold">{takaSigned(d.nav)}</div>
              <div className="text-[11px] text-muted">{t("news.navHint")}</div>
            </div>
          )}
        </div>
        {d.eps_trend && (
          <span className={`inline-block mt-2 text-[11px] font-semibold rounded-full px-2 py-0.5 ${loss ? "text-down bg-down/10" : "text-up bg-up/10"}`}>
            {t(`news.trend.${d.eps_trend}`)}
          </span>
        )}
        <Explainer text={t("news.explain.earnings")} />
      </div>
    );
  }

  if (n.category === "dividend") {
    return (
      <div className="mt-2">
        {d.no_dividend ? (
          <div className="text-sm font-semibold">
            {t("news.div.none")}{" "}
            {d.year_ended && <span className="text-muted font-normal">{fill("news.div.forYear", { year: shortDate(d.year_ended) })}</span>}
          </div>
        ) : (
          <>
            {d.cash_pct != null && (
              <div className="text-sm font-semibold text-up">
                {fill("news.div.cash", { pct: d.cash_pct })}{" "}
                {d.per_share_cash != null && <span>{fill("news.div.perShare", { amt: d.per_share_cash.toFixed(2) })}</span>}
              </div>
            )}
            {d.stock_pct != null && <div className="text-sm">{fill("news.div.stock", { pct: d.stock_pct })}</div>}
            {d.per_share_cash != null && (
              <div className="bg-up/10 rounded-xl px-3 py-2 mt-2 text-xs text-text/90 leading-relaxed">
                {fill("news.div.example", { amt: (d.per_share_cash * 100).toFixed(0) })}
                <div className="text-muted mt-1">{fill("news.div.priceAdj", { amt: d.per_share_cash.toFixed(2) })}</div>
              </div>
            )}
          </>
        )}
        {d.agm_date && (
          <div className="flex mt-2 border border-border rounded-xl divide-x divide-border">
            <DateCell label={t("news.agm")} value={shortDate(d.agm_date)} />
          </div>
        )}
      </div>
    );
  }

  if (n.category === "board_meeting" && d.meeting_date) {
    const parts = (d.agenda ?? []).map((a) =>
      a === "financials" ? fill("news.board.financials", { period: t(`news.period.${d.period ?? "annual"}`) }) : t("news.board.dividend"),
    );
    return (
      <div className="mt-2">
        <p className="text-sm font-semibold">
          {fill("news.board.title", { date: shortDate(d.meeting_date), what: parts.join(t("news.board.and")) })}
        </p>
        <Explainer text={t("news.explain.board")} />
      </div>
    );
  }

  if ((n.category === "corporate_action" || n.category === "halt") && (d.record_date || d.spot_from)) {
    return (
      <div className="mt-2">
        <div className="flex border border-border rounded-xl divide-x divide-border">
          {d.spot_from && <DateCell label={t("news.spotMarket")} value={`${shortDate(d.spot_from)}–${shortDate(d.spot_to)}`} />}
          <DateCell label={t("news.recordDate")} value={shortDate(d.record_date)} accent />
          {d.agm_date && <DateCell label={t("news.agm")} value={shortDate(d.agm_date)} />}
        </div>
        <Explainer text={t("news.explain.dates")} />
      </div>
    );
  }

  if (n.category === "rating" && (d.long_term || d.short_term)) {
    return (
      <div className="mt-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-semibold">{fill("news.rating.line", { lt: d.long_term ?? "—", st: d.short_term ?? "—" })}</span>
          {d.outlook && <span className="text-xs text-muted">{fill("news.rating.outlook", { outlook: d.outlook })}</span>}
          {d.action && (
            <span className={`text-[11px] font-semibold rounded-full px-2 py-0.5 ${d.action === "upgrade" ? "text-up bg-up/10" : "text-down bg-down/10"}`}>
              {t(`news.rating.${d.action}`)}
            </span>
          )}
        </div>
        <Explainer text={t("news.explain.rating")} />
      </div>
    );
  }

  return null;
}

// A routine notice as a single timeline row — dot, terse description, date. Keeps board-meeting
// schedules and bare ratings from each eating a whole card.
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
function Digest({ items }: { items: NewsItem[] }) {
  const { t } = useLang();
  const div = items.find(
    (n) => n.category === "dividend" && (n.details?.cash_pct != null || n.details?.stock_pct != null),
  );
  const earn = items.find((n) => n.category === "earnings" && n.details?.eps_current != null);
  const earnings = items
    .filter((n) => n.category === "earnings" && n.details?.eps_current != null)
    .slice(0, 4);
  const upCount = earnings.filter((n) => (n.details!.eps_current as number) > 0).length;
  const rating = items.find((n) => n.category === "rating");

  const cells: { label: string; value: ReactNode; sub?: string }[] = [];
  if (div) {
    const dd = div.details!;
    const cash = dd.cash_pct != null ? fillT(t, "news.digest.cash", { pct: dd.cash_pct }) : "";
    const bonus = dd.stock_pct != null ? fillT(t, "news.digest.bonus", { pct: dd.stock_pct }) : "";
    cells.push({
      label: t("news.digest.dividend"),
      value: (
        <span className="text-up">
          {cash}
          {bonus}
        </span>
      ),
      sub:
        dd.per_share_cash != null
          ? fillT(t, "news.div.perShare", { amt: dd.per_share_cash.toFixed(2) })
          : undefined,
    });
  }
  if (earn) {
    const ed = earn.details!;
    const good =
      ed.eps_trend === "up" || ed.eps_trend === "to_profit" || ed.eps_trend === "loss_narrowed";
    const flat = ed.eps_trend === "flat" || !ed.eps_trend;
    cells.push({
      label: t("news.digest.eps"),
      value: (
        <span>
          {takaSigned(ed.eps_current as number)}{" "}
          {!flat && <span className={good ? "text-up" : "text-down"}>{good ? "▲" : "▼"}</span>}
        </span>
      ),
      sub: ed.period ? t(`news.period.${ed.period}`) : undefined,
    });
  }
  if (earnings.length) {
    cells.push({
      label: t("news.digest.streak"),
      value: fillT(t, "news.digest.streakVal", { n: upCount, m: earnings.length }),
    });
  }
  if (rating) {
    cells.push({
      label: t("news.digest.rating"),
      value: fillT(t, "news.digest.rated", { date: discMonth(rating.published_at) }),
    });
  }
  if (!cells.length) return null;
  return (
    <div>
      <div className="text-[11px] text-muted mb-1.5 px-1">{t("news.digest.title")}</div>
      <div className="grid grid-cols-2 gap-2">
        {cells.map((c, i) => (
          <div key={i} className="bg-bg/40 rounded-xl px-3 py-2">
            <div className="text-[11px] text-muted">{c.label}</div>
            <div className="text-sm font-bold">{c.value}</div>
            {c.sub && <div className="text-[11px] text-muted">{c.sub}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}

export function NewsPanel({ items }: { items: NewsItem[] }) {
  const { t } = useLang();
  const [filter, setFilter] = useState<string>("all");
  if (!items.length) return <Empty>{t("news.empty")}</Empty>;
  const today = new Date().toISOString().slice(0, 10);
  const upcoming = (n: NewsItem): boolean =>
    (n.category === "board_meeting" && isFuture(n.details?.meeting_date, today)) ||
    ((n.category === "corporate_action" || n.category === "halt") &&
      isFuture(n.details?.record_date, today));

  const FILTERS: [string, string][] = [
    ["all", t("news.filter.all")],
    ["earnings", t("news.filter.earnings")],
    ["dividend", t("news.filter.dividend")],
    ["board_meeting", t("news.filter.meeting")],
    ["rating", t("news.filter.rating")],
  ];
  const timeline = items
    .filter((n) => !upcoming(n))
    .filter((n) => filter === "all" || n.category === filter);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex gap-1.5 overflow-x-auto -mx-1 px-1 pb-0.5">
        {FILTERS.map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => setFilter(key)}
            className={`shrink-0 text-[12px] rounded-full px-3 py-1 border ${
              filter === key ? "bg-text text-bg border-text font-semibold" : "text-muted border-border"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <UpcomingStrip items={items} today={today} />
      <Digest items={items} />

      <div className="flex flex-col gap-2">
        {timeline.map((n, i) =>
          n.category === "board_meeting" || !hasDecoded(n) ? (
            <CompactRow key={i} n={n} />
          ) : (
            <div key={i} className="bg-surface border border-border rounded-2xl p-3">
              <div className="flex items-center gap-2 text-[11px]">
                <span className={`font-semibold rounded-full px-2 py-0.5 ${catChip(n.category)}`}>
                  {catName(n.category, t)}
                </span>
                <span className="text-muted tnum">{n.published_at}</span>
              </div>
              <p className="text-sm font-semibold mt-2">{n.headline}</p>
              <DecodedBody n={n} />
            </div>
          ),
        )}
      </div>
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

const OWN_GREEN = "#16c784";

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
            🚀 Smart money is building a stake
          </div>
          <div className="text-[12px] text-muted mt-0.5">
            Institutions + foreign investors now hold <b className="text-fg">{smartNow.toFixed(1)}%</b>,
            up from {smartThen.toFixed(1)}% in {discMonth(first.as_of)}.
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
          </span>
          {chip(stepDelta(c.key))}
          <span className="text-sm font-semibold tnum w-16 text-right">{pct(c.v)}</span>
        </div>
      ))}

      <p className="text-[10px] text-muted mt-2">
        Free float ~{freeFloat.toFixed(0)}%.{" "}
        {hist.length > 1 ? `${hist.length} disclosures, ${discMonth(hist[0].as_of)}–${discMonth(o.as_of ?? hist[hist.length - 1].as_of)}. ` : ""}
        ▲▼ = change vs the prior disclosure. Descriptive, not advice.
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
