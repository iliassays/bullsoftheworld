import type { Company, NewsItem } from "../lib/api";
import { Empty } from "./ui";
import { InfoTip } from "./InfoTip";
import { Sparkline } from "./Sparkline";

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

const CAT_LABEL: Record<string, string> = {
  dividend: "Dividend",
  earnings: "Earnings",
  rating: "Rating",
  board_meeting: "Board meeting",
  corporate_action: "Corporate action",
  halt: "Halt",
  psi: "Price-sensitive",
  other: "Other",
};

export function NewsPanel({ items }: { items: NewsItem[] }) {
  if (!items.length) return <Empty>No news yet for this stock.</Empty>;
  return (
    <div className="flex flex-col gap-2">
      {items.map((n, i) => (
        <div
          key={i}
          className="bg-surface border border-border rounded-2xl p-3"
        >
          <div className="flex items-center gap-2 text-[11px]">
            <span className="text-accent font-semibold bg-accent/10 rounded-full px-2 py-0.5">
              {CAT_LABEL[n.category] ?? n.category}
            </span>
            <span className="text-muted">{n.published_at}</span>
            <span className="ml-auto text-muted">strength {n.strength}</span>
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
      <p className="text-[10px] text-muted">
        Exchange disclosures. Descriptive, not advice.
      </p>
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
  const yoy =
    f.eps_growth_yoy == null
      ? dash
      : `${f.eps_growth_yoy > 0 ? "+" : ""}${f.eps_growth_yoy.toFixed(1)}%`;
  return (
    <Card title="Fundamentals">
      <Row label="Market cap" value={crore(f.market_cap_mn)} help={F_HELP.market_cap} />
      <Row label="P/E" value={ratio(f.pe_ratio)} help={F_HELP.pe} />
      <Row
        label="P/E vs sector"
        value={f.pe_vs_sector == null ? dash : `${f.pe_vs_sector.toFixed(2)}×`}
        help={F_HELP.pe_sector}
      />
      <Row label="P/B" value={ratio(f.pb_ratio)} help={F_HELP.pb} />
      <Row label="Dividend yield" value={pct(f.dividend_yield)} help={F_HELP.yield} />
      <Row label="EPS (annual)" value={taka(f.eps)} help={F_HELP.eps} />
      <Row label="EPS growth (YoY)" value={yoy} help={F_HELP.eps_growth} />
      <Row label="NAV / share" value={taka(f.nav_per_share)} help={F_HELP.nav} />
      <Row
        label="52-week range"
        value={`${taka(f.week52_low)} – ${taka(f.week52_high)}`}
      />
      <Row label="Free-float cap" value={crore(f.free_float_cap_mn)} />
      <Row
        label="Shares outstanding"
        value={
          f.outstanding_shares == null
            ? dash
            : f.outstanding_shares.toLocaleString()
        }
      />
      <Row label="Face value" value={taka(f.face_value)} />
      <Row label="Sector" value={f.sector ?? dash} />
      <Row label="Credit rating" value={f.credit_rating ?? dash} />
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

export function OwnershipPanel({ o }: { o: Company["ownership"] }) {
  const segs = [
    { key: "sponsor", label: "Sponsor / Director", v: o.sponsor_pct, color: "var(--color-accent)" },
    { key: "institute", label: "Institutional", v: o.institute_pct, color: "#0ea5e9" },
    { key: "foreign", label: "Foreign", v: o.foreign_pct, color: "var(--color-up)" },
    { key: "public", label: "Public", v: o.public_pct, color: "var(--color-muted)" },
  ] as const;
  const known = segs.some((s) => s.v != null);
  if (!known) return <Empty>No ownership disclosure yet.</Empty>;

  const hist = o.history ?? [];
  const freeFloat = (o.institute_pct ?? 0) + (o.foreign_pct ?? 0) + (o.public_pct ?? 0);
  // DSE re-discloses irregularly; flag when the latest disclosure is well over half a year old so
  // an old change doesn't read as fresh news.
  const stale =
    o.as_of != null && (Date.now() - new Date(o.as_of).getTime()) / 86_400_000 > 270;

  const deltaEl = (d: number | null) =>
    d == null || Math.abs(d) < 0.01 ? null : (
      <span className={d > 0 ? "text-up" : "text-down"}>
        {" "}
        ({d > 0 ? "+" : ""}
        {d.toFixed(2)}pp)
      </span>
    );

  return (
    <Card title="Ownership">
      <div className="rounded-xl bg-card border border-border p-3 mb-3">
        {stale ? (
          <div className="text-[13px] leading-snug text-muted">
            ⏳ Latest disclosure {o.as_of ? discMonth(o.as_of) : dash} — DSE hasn't filed a newer one
            for this stock, so the figures below may be out of date.
          </div>
        ) : (
          <div className="text-[13px] leading-snug">🏦 {smartMoneyRead(o)}</div>
        )}
        <div className="text-[11px] text-muted mt-1">
          Free float ~{freeFloat.toFixed(0)}% — the slice held by public, institutions and foreigners
          that actually trades.
        </div>
      </div>

      <div className="text-[10px] uppercase tracking-wide text-muted/70 mb-1">
        Latest split{o.as_of ? ` · ${discMonth(o.as_of)}` : ""}
      </div>
      <div className="flex h-3 rounded-full overflow-hidden mb-3">
        {segs.map((s) => (
          <div key={s.key} style={{ width: `${s.v ?? 0}%`, backgroundColor: s.color }} />
        ))}
      </div>

      {segs.map((s) => {
        const series = hist.map((p) => p[s.key]).filter((x): x is number => x != null);
        const d =
          series.length >= 2 ? series[series.length - 1] - series[series.length - 2] : null;
        return (
          <div key={s.key} className="flex items-center gap-3 py-2 border-b border-border/60">
            <span className="flex items-center gap-2 flex-1 min-w-0">
              <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: s.color }} />
              <span className="text-xs text-muted truncate">{s.label}</span>
            </span>
            {series.length >= 2 && <Sparkline data={series} />}
            <span className="text-sm font-semibold tnum whitespace-nowrap shrink-0">
              {pct(s.v)}
              {deltaEl(d)}
            </span>
          </div>
        );
      })}

      <p className="text-[10px] text-muted mt-2">
        {hist.length > 1
          ? `Trend across ${hist.length} disclosures: ${hist.map((p) => discMonth(p.as_of)).join(" · ")}. `
          : ""}
        Change (pp) is vs the prior disclosure. Descriptive, not advice.
      </p>
    </Card>
  );
}

export function EarningsPanel({
  earnings,
  dividends,
}: {
  earnings: Company["earnings"];
  dividends: Company["dividends"];
}) {
  if (!earnings.length && !dividends.length)
    return <Empty>No earnings history yet.</Empty>;
  return (
    <div className="flex flex-col gap-3">
      {earnings.length > 0 && (
        <Card title="Earnings history">
          <div className="grid grid-cols-4 text-[11px] text-muted font-semibold pb-1 border-b border-border">
            <span>FY</span>
            <span className="text-right">EPS</span>
            <span className="text-right">NAV</span>
            <span className="text-right">Profit</span>
          </div>
          {earnings.slice(0, 8).map((e) => (
            <div
              key={e.fiscal_year}
              className="grid grid-cols-4 text-sm tnum py-1.5 border-b border-border/60 last:border-0"
            >
              <span>{e.fiscal_year}</span>
              <span className="text-right">{taka(e.eps)}</span>
              <span className="text-right">{taka(e.nav_per_share)}</span>
              <span className="text-right text-muted">
                {crore(e.profit_mn)}
              </span>
            </div>
          ))}
        </Card>
      )}
      {dividends.length > 0 && (
        <Card title="Dividend history">
          <div className="grid grid-cols-3 text-[11px] text-muted font-semibold pb-1 border-b border-border">
            <span>Year</span>
            <span className="text-right">Cash</span>
            <span className="text-right">Bonus</span>
          </div>
          {dividends.slice(0, 8).map((d) => (
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
