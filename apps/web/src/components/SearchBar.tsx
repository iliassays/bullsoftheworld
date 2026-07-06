import { useEffect, useRef, useState } from "react";
import { useLang } from "../lib/i18n";
import { useNavigate } from "../lib/nav";
import { api, type SymbolOut } from "../lib/api";
import { CompanyLogo } from "./CompanyLogo";

// Global ticker search — instant client-side typeahead over the (small) symbol universe.
// The list is fetched once and module-cached so it loads at most once per session.
let symbolCache: SymbolOut[] | null = null;

export function SearchBar() {
  const { t } = useLang();
  const [q, setQ] = useState("");
  const [symbols, setSymbols] = useState<SymbolOut[]>(symbolCache ?? []);
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  const load = () => {
    if (symbolCache) return;
    api
      .symbols(500)
      .then((s) => {
        symbolCache = s;
        setSymbols(s);
      })
      .catch(() => {});
  };

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const raw = q.trim();
  const upper = raw.toUpperCase();
  const results = raw
    ? symbols
        .filter(
          (s) =>
            s.code.includes(upper) ||
            s.name_en.toUpperCase().includes(upper) ||
            (s.name_bn ?? "").includes(raw),
        )
        .slice(0, 8)
    : [];

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
          load();
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
