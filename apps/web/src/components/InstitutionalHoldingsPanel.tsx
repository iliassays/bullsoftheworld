import { useMemo, useState } from "react";
import type { InstitutionalActivity, InstitutionalPosition } from "../lib/api";
import { useLang } from "../lib/i18n";
import { formatMoney } from "../lib/market";
import { Empty } from "./ui";

type View = "largest" | "new" | "added" | "trimmed" | "exited";

const compactUsd = (value: number) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);

const signedPct = (value: number | null) =>
  value == null ? "—" : `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;

function PositionRows({ rows, bn }: { rows: InstitutionalPosition[]; bn: boolean }) {
  if (!rows.length) {
    return <Empty>{bn ? "এই বিভাগে কোনো রিপোর্ট করা পরিবর্তন নেই।" : "No reported changes in this category."}</Empty>;
  }
  return (
    <div className="divide-y divide-border/60">
      {rows.map((row) => (
        <a
          key={row.manager_cik}
          href={row.url}
          target="_blank"
          rel="noreferrer"
          className="grid grid-cols-[minmax(0,1fr)_auto] gap-3 py-2.5"
        >
          <div className="min-w-0">
            <div className="text-[13px] font-semibold truncate">{row.manager_name}</div>
            <div className="text-[10px] text-muted mt-0.5">
              {bn ? "প্রকাশিত" : "Filed"} {row.filing_date} · {row.shares.toLocaleString()} {bn ? "শেয়ার" : "shares"}
            </div>
          </div>
          <div className="text-right tnum">
            <div className="text-[12px] font-semibold">{compactUsd(row.value_usd)}</div>
            <div
              className={`text-[10px] ${
                (row.share_change ?? 0) > 0
                  ? "text-up"
                  : (row.share_change ?? 0) < 0
                    ? "text-down"
                    : "text-muted"
              }`}
            >
              {row.change_type} {row.change_pct == null ? "" : signedPct(row.change_pct)}
            </div>
          </div>
        </a>
      ))}
    </div>
  );
}

export function InstitutionalHoldingsPanel({ data }: { data: InstitutionalActivity }) {
  const { lang } = useLang();
  const bn = lang === "bn";
  const [view, setView] = useState<View>("largest");
  const latest = data.periods[0];
  const rows = useMemo(
    () =>
      ({
        largest: data.top_positions,
        new: data.top_new,
        added: data.top_increases,
        trimmed: data.top_reductions,
        exited: data.top_exits,
      })[view],
    [data, view],
  );

  if (!latest)
    return (
      <Empty>
        {bn
          ? "এই সিকিউরিটির জন্য নির্ভরযোগ্যভাবে মেলানো Form 13F ইতিহাস এখনো নেই।"
          : data.disclosure_note}
      </Empty>
    );

  const views: Array<{ id: View; en: string; bn: string }> = [
    { id: "largest", en: "Largest", bn: "সবচেয়ে বড়" },
    { id: "new", en: "New", bn: "নতুন" },
    { id: "added", en: "Added", bn: "বাড়িয়েছে" },
    { id: "trimmed", en: "Trimmed", bn: "কমিয়েছে" },
    { id: "exited", en: "Exited", bn: "বেরিয়েছে" },
  ];

  return (
    <section className="bg-surface border border-border rounded-2xl p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">{bn ? "প্রাতিষ্ঠানিক হোল্ডিং" : "Institutional holdings"}</h2>
          <p className="text-[11px] text-muted mt-1">
            {bn ? "SEC Form 13F · ত্রৈমাসিক প্রকাশ" : "SEC Form 13F · quarterly disclosure"}
          </p>
        </div>
        <a
          href={latest.source_url}
          target="_blank"
          rel="noreferrer"
          className="shrink-0 text-xs font-semibold text-accent"
        >
          SEC ↗
        </a>
      </div>

      <div className="mt-3 border-y border-border py-3">
        <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 text-center">
          <div>
            <div className="text-[10px] text-muted">{bn ? "হোল্ডিং তারিখ" : "Holdings date"}</div>
            <div className="text-xs font-semibold tnum">{latest.report_date}</div>
          </div>
          <div className="text-muted" aria-hidden>→</div>
          <div>
            <div className="text-[10px] text-muted">{bn ? "সর্বশেষ প্রকাশ" : "Latest public filing"}</div>
            <div className="text-xs font-semibold tnum">{latest.public_by}</div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-x-4 mt-2">
        <div className="py-2 border-b border-border/60">
          <div className="text-[10px] text-muted">{bn ? "রিপোর্টিং ম্যানেজার" : "Reporting managers"}</div>
          <div className="text-base font-semibold tnum">{latest.managers_count.toLocaleString()}</div>
        </div>
        <div className="py-2 border-b border-border/60">
          <div className="text-[10px] text-muted">{bn ? "মোট প্রকাশিত মূল্য" : "Reported value"}</div>
          <div className="text-base font-semibold tnum">{compactUsd(latest.total_value_usd)}</div>
        </div>
        <div className="py-2 border-b border-border/60">
          <div className="text-[10px] text-muted">{bn ? "তুলনাযোগ্য শেয়ার পরিবর্তন" : "Comparable share change"}</div>
          <div className={`text-base font-semibold tnum ${(latest.net_change_pct ?? 0) >= 0 ? "text-up" : "text-down"}`}>
            {signedPct(latest.net_change_pct)}
          </div>
        </div>
        <div className="py-2 border-b border-border/60">
          <div className="text-[10px] text-muted">{bn ? "প্রকাশের পর রিটার্ন" : "Return since public"}</div>
          <div className={`text-base font-semibold tnum ${(latest.return_since_public_pct ?? 0) >= 0 ? "text-up" : "text-down"}`}>
            {signedPct(latest.return_since_public_pct)}
          </div>
          {latest.close_on_public_date != null && (
            <div className="text-[9px] text-muted tnum">
              {formatMoney(latest.close_on_public_date)} → {latest.latest_close == null ? "—" : formatMoney(latest.latest_close)}
            </div>
          )}
        </div>
      </div>

      <div className="mt-3 text-[11px] text-muted">
        {bn
          ? `নতুন ${latest.new_positions} · বাড়িয়েছে ${latest.increased_positions} · কমিয়েছে ${latest.reduced_positions} · বেরিয়েছে ${latest.exited_positions}`
          : `New ${latest.new_positions} · added ${latest.increased_positions} · trimmed ${latest.reduced_positions} · exited ${latest.exited_positions}`}
      </div>

      <div className="mt-4 flex gap-2 overflow-x-auto pb-1">
        {views.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => setView(item.id)}
            className={`shrink-0 rounded-full border px-3 py-1.5 text-xs font-semibold ${
              view === item.id
                ? "border-accent bg-accent/10 text-accent"
                : "border-border text-muted"
            }`}
          >
            {bn ? item.bn : item.en}
          </button>
        ))}
      </div>
      <PositionRows rows={rows} bn={bn} />

      <div className="mt-3 border-t border-border pt-3 text-[10px] text-muted leading-relaxed">
        <p>
          {bn
            ? "Form 13F ত্রৈমাসিক শেষের হোল্ডিং দেখায় এবং ৪৫ দিন পরে প্রকাশিত হতে পারে। দামের তুলনা ফাইলিং প্রকাশের পর থেকে শুরু হয়েছে, ম্যানেজারের ট্রেডের সময় থেকে নয়।"
            : data.disclosure_note}
        </p>
        <p className="mt-1">
          {bn
            ? "13F সঠিক ট্রেডের তারিখ, এন্ট্রি দাম বা শর্ট পজিশন দেখায় না। অপশন ও অমীমাংসিত CUSIP এখানে বাদ দেওয়া হয়েছে।"
            : data.limitations.join(" ")}
        </p>
      </div>
    </section>
  );
}
