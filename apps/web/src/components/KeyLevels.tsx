import { useEffect, useState } from "react";
import { api } from "../lib/api";

type Levels = { lines: string[]; live_line: string | null };

// "Key levels & what to watch" — deterministic, descriptive scenarios (breakout/support/RSI),
// rendered from server templates. Educational, never a prediction or a call.
export function KeyLevels({ code }: { code: string }) {
  const [data, setData] = useState<Levels | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    setData(null);
    setMissing(false);
    api
      .levels(code)
      .then((r) => setData({ lines: r.lines, live_line: r.live_line }))
      .catch(() => setMissing(true));
  }, [code]);

  if (missing || !data || data.lines.length === 0) return null;

  const body = data.lines.slice(0, -1); // last line is the "not advice" disclaimer
  const footer = data.lines[data.lines.length - 1];

  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <div className="text-accent font-semibold text-sm">🎯 Key levels &amp; what to watch</div>

      {/* Live (delayed) bridge — only present while the market is open */}
      {data.live_line && (
        <div className="mt-3 flex items-start gap-2 bg-card border border-border rounded-xl px-3 py-2">
          <span className="relative flex h-2 w-2 mt-1.5 shrink-0">
            <span className="absolute inline-flex h-full w-full rounded-full bg-up opacity-60 animate-ping" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-up" />
          </span>
          <span className="text-[13px] leading-relaxed text-text/90" lang="bn">
            {data.live_line}
          </span>
        </div>
      )}

      <ul className="mt-3 flex flex-col gap-2">
        {body.map((line, i) => (
          <li key={i} className="text-[14px] leading-relaxed text-text/90 flex gap-2">
            <span className="text-accent">•</span>
            <span lang="bn">{line}</span>
          </li>
        ))}
      </ul>
      <p className="text-[10px] text-muted mt-3" lang="bn">
        {footer}
      </p>
    </div>
  );
}
