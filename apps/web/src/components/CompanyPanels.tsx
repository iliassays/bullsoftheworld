import type { ReactNode } from "react";
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

export function NewsPanel({ items }: { items: NewsItem[] }) {
  const { t } = useLang();
  if (!items.length) return <Empty>{t("news.empty")}</Empty>;
  const catLabel = (c: string) => {
    const tr = t(`cat.${c}`);
    return tr.startsWith("cat.") ? c : tr;
  };
  return (
    <div className="flex flex-col gap-2">
      {items.map((n, i) => (
        <div
          key={i}
          className="bg-surface border border-border rounded-2xl p-3"
        >
          <div className="flex items-center gap-2 text-[11px]">
            <span className="text-accent font-semibold bg-accent/10 rounded-full px-2 py-0.5">
              {catLabel(n.category)}
            </span>
            <span className="text-muted">{n.published_at}</span>
            <span className="ml-auto text-muted">{t("news.strength")} {n.strength}</span>
          </div>
          <div className="mt-1 h-1 rounded-full bg-border overflow-hidden">
            <div
              className="h-full bg-accent"
              style={{ width: `${n.strength}%` }}
            />
          </div>
          <p className="text-sm text-text/90 mt-2">{n.headline}</p>
        </div>
      ))}
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
      <div className="text-accent font-semibold text-sm mb-1">{title}</div>
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
