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

const changeLabel = (value: InstitutionalPosition["change_type"], bn: boolean) => {
  if (!bn) return value === "new" ? "First reported" : value;
  return {
    new: "প্রথম রিপোর্ট",
    increased: "বাড়িয়েছে",
    reduced: "কমিয়েছে",
    unchanged: "অপরিবর্তিত",
    exited: "বেরিয়েছে",
  }[value];
};

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
              {changeLabel(row.change_type, bn)} {row.change_pct == null ? "" : signedPct(row.change_pct)}
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
    { id: "new", en: "First reported", bn: "প্রথম রিপোর্ট" },
    { id: "added", en: "Added", bn: "বাড়িয়েছে" },
    { id: "trimmed", en: "Trimmed", bn: "কমিয়েছে" },
    { id: "exited", en: "Exited", bn: "বেরিয়েছে" },
  ];

  return (
    <section className="bg-surface border border-border rounded-lg p-4">
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

      <div className="mt-3 flex flex-wrap items-center gap-2 text-[10px]">
        <span className="border border-border px-2 py-1 text-muted">
          {bn
            ? `${data.history_quarters}/${data.target_history_quarters} প্রান্তিক ইতিহাস`
            : `${data.history_quarters}/${data.target_history_quarters} quarters loaded`}
        </span>
        <span className="border border-border px-2 py-1 text-muted">
          {bn
            ? `${data.identifier_count}টি যাচাইকৃত CUSIP`
            : `${data.identifier_count} verified CUSIP${data.identifier_count === 1 ? "" : "s"}`}
        </span>
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
          <div className="text-[10px] text-muted">
            {bn ? "রিপোর্ট করা মোট শেয়ারের পরিবর্তন" : "Aggregate reported share change"}
          </div>
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
        <div className="py-2 border-b border-border/60">
          <div className="text-[10px] text-muted">{bn ? "ম্যানেজার প্রবণতা" : "Manager breadth"}</div>
          <div className={`text-base font-semibold tnum ${(latest.net_breadth_pct ?? 0) >= 0 ? "text-up" : "text-down"}`}>
            {signedPct(latest.net_breadth_pct)}
          </div>
          <div className="text-[9px] text-muted tnum">
            {bn
              ? `${latest.adding_managers} বাড়িয়েছে · ${latest.reducing_managers} কমিয়েছে`
              : `${latest.adding_managers} adding · ${latest.reducing_managers} reducing`}
          </div>
        </div>
        <div className="py-2 border-b border-border/60">
          <div className="text-[10px] text-muted">{bn ? "SPY-এর তুলনায় ৩০ সেশন" : "30-session excess vs SPY"}</div>
          <div className={`text-base font-semibold tnum ${(latest.excess_return_30_sessions_pct ?? 0) >= 0 ? "text-up" : "text-down"}`}>
            {signedPct(latest.excess_return_30_sessions_pct)}
          </div>
          <div className="text-[9px] text-muted tnum">
            {bn ? "শুধু প্রকাশের পর" : "Post-public only"}
          </div>
        </div>
      </div>

      <div className="mt-3 text-[11px] text-muted">
        {bn
          ? `প্রথম রিপোর্ট ${latest.new_positions} · বাড়িয়েছে ${latest.increased_positions} · কমিয়েছে ${latest.reduced_positions} · বেরিয়েছে ${latest.exited_positions}`
          : `First reported ${latest.new_positions} · added ${latest.increased_positions} · trimmed ${latest.reduced_positions} · exited ${latest.exited_positions}`}
      </div>
      <p className="mt-1 text-[10px] leading-snug text-muted">
        {bn
          ? "‘প্রথম রিপোর্ট’ মানে তুলনাযোগ্য লোড করা ইতিহাসে প্রথম দেখা; এটি নতুন কেনাকাটার প্রমাণ নয়।"
          : "First reported means first seen in the loaded comparable history; it does not prove a new purchase."}
      </p>

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

      {data.horizons.length > 0 && (
        <div className="mt-5 border-t border-border pt-4">
          <h3 className="text-xs font-semibold">{bn ? "বহু-প্রান্তিক প্রবণতা" : "Multi-quarter direction"}</h3>
          <div className="mt-2 divide-y divide-border/60">
            {data.horizons.map((horizon) => (
              <div key={horizon.quarters} className="grid grid-cols-[1fr_auto] gap-3 py-2">
                <div>
                  <div className="text-[11px] font-medium">
                    {bn ? `${horizon.quarters} প্রান্তিক` : `${horizon.quarters}-quarter snapshots`}
                  </div>
                  <div className="text-[9px] text-muted tnum">
                    {horizon.from_report_date} → {horizon.to_report_date}
                  </div>
                </div>
                <div className={`text-sm font-semibold tnum ${horizon.reported_share_change_pct >= 0 ? "text-up" : "text-down"}`}>
                  {signedPct(horizon.reported_share_change_pct)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {data.manager_histories.length > 0 && (
        <div className="mt-5 border-t border-border pt-4">
          <div className="flex items-baseline justify-between gap-3">
            <h3 className="text-xs font-semibold">{bn ? "নির্বাচিত ম্যানেজারের ইতিহাস" : "Selected manager history"}</h3>
            <span className="text-[9px] text-muted">{bn ? "CIK অনুযায়ী" : "CIK identity"}</span>
          </div>
          <div className="mt-2 divide-y divide-border/60">
            {data.manager_histories.slice(0, 5).map((manager) => (
              <div key={manager.manager_cik} className="py-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate text-[11px] font-semibold">{manager.manager_name}</div>
                    <div className="text-[9px] text-muted tnum">CIK {manager.manager_cik}</div>
                  </div>
                  <div className="shrink-0 text-[11px] font-semibold tnum">{compactUsd(manager.latest_value_usd)}</div>
                </div>
                <div className="mt-2 flex gap-1.5 overflow-x-auto pb-1">
                  {manager.points.map((point) => (
                    <a
                      key={point.report_date}
                      href={point.url}
                      target="_blank"
                      rel="noreferrer"
                      className="min-w-[92px] border-l-2 border-border pl-2"
                    >
                      <div className="text-[9px] text-muted tnum">{point.report_date}</div>
                      {point.reported_manager_name !== manager.manager_name && (
                        <div className="max-w-[90px] truncate text-[8px] text-muted" title={point.reported_manager_name}>
                          {point.reported_manager_name}
                        </div>
                      )}
                      <div className={`text-[10px] font-semibold ${(point.share_change ?? 0) > 0 ? "text-up" : (point.share_change ?? 0) < 0 ? "text-down" : "text-muted"}`}>
                        {changeLabel(point.change_type, bn)}
                      </div>
                      <div className="text-[9px] tnum">{signedPct(point.change_pct)}</div>
                    </a>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

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
        {data.bounded_manager_history && (
          <p className="mt-1">
            {bn
              ? "ম্যানেজার ইতিহাসে প্রতি প্রান্তিকের গুরুত্বপূর্ণ সংরক্ষিত অবস্থান দেখানো হয়; একই নামের ম্যানেজার একত্র করা হয় না।"
              : "Manager history uses material retained positions per quarter; managers with similar names are not merged."}
          </p>
        )}
      </div>
    </section>
  );
}
