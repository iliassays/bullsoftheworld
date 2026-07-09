import { useEffect, useRef, useState } from "react";
import { useLang } from "../lib/i18n";
import { useNavigate } from "../lib/nav";
import type { SymbolOut } from "../lib/api";
import { searchSymbols } from "../lib/symbols";
import { CompanyLogo } from "./CompanyLogo";

export function SearchBar() {
  const { t } = useLang();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<SymbolOut[]>([]);
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const raw = q.trim();
  useEffect(() => {
    if (!open || !raw) {
      setResults([]);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      searchSymbols(raw, 8).then((symbols) => {
        if (!cancelled) setResults(symbols);
      });
    }, 120);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [open, raw]);

  const go = (code: string) => {
    setQ("");
    setOpen(false);
    navigate(`/s/${code}`);
  };

  return (
    <div ref={boxRef} className="relative">
      <input
        value={q}
        onFocus={() => {
          setOpen(true);
        }}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && results[0]) go(results[0].code);
          if (e.key === "Escape") setOpen(false);
        }}
        placeholder={`🔍 ${t("search.placeholder")}`}
        className="w-full bg-card border border-border rounded-xl px-3 py-1.5 text-sm outline-none focus:border-accent"
      />
      {open && results.length > 0 && (
        <div className="absolute left-0 right-0 mt-1 bg-surface border border-border rounded-xl overflow-hidden z-50 shadow-lg">
          {results.map((s) => (
            <button
              key={s.code}
              onMouseDown={() => go(s.code)}
              className="w-full text-left px-3 py-2 hover:bg-card flex items-center gap-2"
            >
              <CompanyLogo code={s.code} size={22} />
              <span className="font-bold text-[13px] text-accent shrink-0">${s.code}</span>
              <span className="text-xs text-muted truncate" lang="bn">
                {s.name_en}
                {s.name_bn ? ` · ${s.name_bn}` : ""}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
