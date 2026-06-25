import type { Company } from "../lib/api";
import { Empty } from "./ui";

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
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="flex items-baseline justify-between py-2 border-b border-border/60 last:border-0">
      <span className="text-xs text-muted">{label}</span>
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
      <Row label="Market cap" value={crore(f.market_cap_mn)} />
      <Row label="P/E" value={ratio(f.pe_ratio)} />
      <Row
        label="P/E vs sector"
        value={f.pe_vs_sector == null ? dash : `${f.pe_vs_sector.toFixed(2)}×`}
      />
      <Row label="P/B" value={ratio(f.pb_ratio)} />
      <Row label="Dividend yield" value={pct(f.dividend_yield)} />
      <Row label="EPS (annual)" value={taka(f.eps)} />
      <Row label="EPS growth (YoY)" value={yoy} />
      <Row label="NAV / share" value={taka(f.nav_per_share)} />
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

export function OwnershipPanel({ o }: { o: Company["ownership"] }) {
  const segs = [
    { label: "Sponsor/Director", v: o.sponsor_pct, cls: "bg-accent" },
    { label: "Institutional", v: o.institute_pct, cls: "bg-sky-500" },
    { label: "Foreign", v: o.foreign_pct, cls: "bg-up" },
    { label: "Public", v: o.public_pct, cls: "bg-muted" },
  ];
  const known = segs.some((s) => s.v != null);
  if (!known) return <Empty>No ownership disclosure yet.</Empty>;
  const delta = (d: number | null) =>
    d == null || d === 0 ? null : (
      <span className={d > 0 ? "text-up" : "text-down"}>
        {" "}
        ({d > 0 ? "+" : ""}
        {d.toFixed(2)}pp)
      </span>
    );
  return (
    <Card title="Ownership">
      <div className="flex h-3 rounded-full overflow-hidden my-2">
        {segs.map((s) => (
          <div
            key={s.label}
            className={s.cls}
            style={{ width: `${s.v ?? 0}%` }}
          />
        ))}
      </div>
      <Row label="Sponsor / Director" value={pct(o.sponsor_pct)} />
      <div className="flex items-baseline justify-between py-2 border-b border-border/60">
        <span className="text-xs text-muted">Institutional</span>
        <span className="text-sm font-semibold tnum">
          {pct(o.institute_pct)}
          {delta(o.institute_delta)}
        </span>
      </div>
      <div className="flex items-baseline justify-between py-2 border-b border-border/60">
        <span className="text-xs text-muted">Foreign</span>
        <span className="text-sm font-semibold tnum">
          {pct(o.foreign_pct)}
          {delta(o.foreign_delta)}
        </span>
      </div>
      <Row label="Public" value={pct(o.public_pct)} />
      <p className="text-[10px] text-muted mt-2">
        As of {o.as_of ?? dash}. Change (pp) vs the prior disclosure.
        Descriptive, not advice.
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
