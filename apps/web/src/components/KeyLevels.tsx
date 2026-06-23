import { useEffect, useState } from "react";
import { api } from "../lib/api";

// "Key levels & what to watch" — deterministic, descriptive scenarios (breakout/support/RSI),
// rendered from server templates. Educational, never a prediction or a call.
export function KeyLevels({ code }: { code: string }) {
  const [lines, setLines] = useState<string[] | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    setLines(null);
    setMissing(false);
    api
      .levels(code)
      .then((r) => setLines(r.lines))
      .catch(() => setMissing(true));
  }, [code]);

  if (missing || !lines || lines.length === 0) return null;

  // last line is the "not advice" disclaimer — style it as a footer
  const body = lines.slice(0, -1);
  const footer = lines[lines.length - 1];

  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <div className="text-accent font-semibold text-sm">🎯 Key levels &amp; what to watch</div>
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
