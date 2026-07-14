import type { ShortVolumeActivity } from "../lib/api";
import { formatOrdinal } from "../lib/format";
import { Sparkline } from "./Sparkline";

const value = (input: number | null, suffix = "%") =>
  input == null ? "-" : `${input > 0 && suffix === " pp" ? "+" : ""}${input.toFixed(1)}${suffix}`;

export function ShortVolumePanel({ data }: { data: ShortVolumeActivity }) {
  const elevated = data.status === "elevated";
  const tone = elevated
    ? "border-warn/40 bg-warn/10 text-warn"
    : "border-border bg-bg text-text";

  return (
    <section className="bg-surface border border-border rounded-lg p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">FINRA short-sale activity</h2>
          <p className="mt-1 text-[11px] text-muted">
            Nightly Reg SHO data {data.as_of_date ? `- ${data.as_of_date}` : ""}
          </p>
        </div>
        {data.source_url && (
          <a
            href={data.source_url}
            target="_blank"
            rel="noreferrer"
            className="shrink-0 text-xs font-semibold text-accent"
          >
            FINRA ↗
          </a>
        )}
      </div>

      <div className={`mt-3 border px-3 py-2.5 ${tone}`}>
        <div className="text-xs font-semibold">{data.status_label}</div>
        <p className="mt-1 text-[10px] leading-relaxed text-muted">{data.interpretation}</p>
      </div>

      {data.short_share_pct != null && (
        <>
          <div className="mt-3 grid grid-cols-2 gap-x-4">
            <div className="border-b border-border/60 py-2">
              <div className="text-[10px] text-muted">Latest short-marked share</div>
              <div className="text-base font-semibold tnum">{value(data.short_share_pct)}</div>
            </div>
            <div className="border-b border-border/60 py-2">
              <div className="text-[10px] text-muted">20-session norm</div>
              <div className="text-base font-semibold tnum">{value(data.average_20_pct)}</div>
            </div>
            <div className="border-b border-border/60 py-2">
              <div className="text-[10px] text-muted">Difference from norm</div>
              <div className="text-base font-semibold tnum">{value(data.deviation_pp, " pp")}</div>
            </div>
            <div className="border-b border-border/60 py-2">
              <div className="text-[10px] text-muted">Reported activity vs norm</div>
              <div className="text-base font-semibold tnum">
                {data.activity_vs_20x == null ? "-" : `${data.activity_vs_20x.toFixed(1)}x`}
              </div>
            </div>
          </div>
          {data.points.length > 1 && (
            <div className="mt-3 flex items-center justify-between gap-4">
              <div>
                <div className="text-[10px] text-muted">Recent short-marked share</div>
                <div className="mt-0.5 text-[9px] text-muted">
                  {data.percentile_60 == null
                    ? `${data.baseline_sessions} baseline sessions`
                    : `${formatOrdinal(data.percentile_60)} percentile of loaded history`}
                </div>
              </div>
              <Sparkline data={data.points.map((point) => point.short_share_pct)} width={118} height={36} />
            </div>
          )}
        </>
      )}

      <details className="mt-4 border-t border-border pt-3">
        <summary className="cursor-pointer text-[10px] font-semibold text-muted">
          What this measures
        </summary>
        <ul className="mt-2 space-y-1 text-[10px] leading-relaxed text-muted">
          {data.limitations.map((item) => (
            <li key={item}>- {item}</li>
          ))}
        </ul>
      </details>
    </section>
  );
}
