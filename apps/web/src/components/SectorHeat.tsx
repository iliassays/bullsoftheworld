import { useEffect, useState } from "react";
import { api, type Sector } from "../lib/api";

// Hot sectors — DSE retail thinks in sectors. A scannable strip of each sector's average move today
// plus its advancers/decliners breadth, hottest first. Descriptive market context.
export function SectorHeat() {
  const [sectors, setSectors] = useState<Sector[] | null>(null);

  useEffect(() => {
    api
      .sectors()
      .then(setSectors)
      .catch(() => setSectors([]));
  }, []);

  if (!sectors || sectors.length === 0) return null;

  return (
    <div className="flex flex-col gap-1">
      <div className="text-[11px] uppercase tracking-wide text-muted px-1">Hot sectors today</div>
      <div className="flex gap-2 overflow-x-auto pb-1">
        {sectors.map((s) => {
          const up = s.avg_change >= 0;
          return (
            <div
              key={s.sector}
              className="shrink-0 w-32 bg-surface border border-border rounded-xl p-2.5"
            >
              <div className="text-[12px] font-semibold truncate">{s.sector}</div>
              <div className={`text-sm font-bold tnum ${up ? "text-up" : "text-down"}`}>
                {up ? "+" : ""}
                {s.avg_change.toFixed(2)}%
              </div>
              <div className="mt-1.5 flex h-1 rounded-full overflow-hidden bg-border">
                <div
                  className="bg-up h-full"
                  style={{ width: `${(s.advancers / s.count) * 100}%` }}
                />
                <div
                  className="bg-down h-full"
                  style={{ width: `${(s.decliners / s.count) * 100}%` }}
                />
              </div>
              <div className="text-[10px] text-muted mt-1 tnum">
                {s.advancers}▲ {s.decliners}▼ · {s.count}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
