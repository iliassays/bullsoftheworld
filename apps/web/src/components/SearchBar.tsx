import { useEffect, useRef, useState } from "react";
import { useLang } from "../lib/i18n";
import { useNavigate } from "../lib/nav";
import { ApiError, api, type SymbolOut } from "../lib/api";
import { searchSymbols } from "../lib/symbols";
import { useTenantConfig } from "../lib/tenant";
import { trackProductEvent } from "../lib/analytics";
import { CompanyLogo } from "./CompanyLogo";

export function SearchBar() {
  const { t } = useLang();
  const { config } = useTenantConfig();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<SymbolOut[]>([]);
  const [open, setOpen] = useState(false);
  const [preparingCode, setPreparingCode] = useState<string | null>(null);
  const [preparationMessage, setPreparationMessage] = useState<string | null>(null);
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

  useEffect(() => {
    if (!preparingCode) return;
    const poll = window.setInterval(() => {
      api.researchPreparation(preparingCode).then((status) => {
        if (status.can_open) {
          window.clearInterval(poll);
          setPreparingCode(null);
          navigate(`/s/${status.code}`);
        } else if (["review_required", "rejected", "failed"].includes(status.status)) {
          window.clearInterval(poll);
          setPreparingCode(null);
          setPreparationMessage(
            status.status === "review_required"
              ? "Research prepared; evidence review is pending."
              : status.status === "rejected"
                ? `Preparation stopped: ${status.failure_reasons.join(", ") || "quality gates failed"}.`
                : "Preparation failed and can be retried.",
          );
        }
      }).catch(() => undefined);
    }, 5000);
    return () => window.clearInterval(poll);
  }, [navigate, preparingCode]);

  const go = async (symbol: SymbolOut, rank = 1) => {
    const code = symbol.code;
    trackProductEvent("select_search_result", {
      stock_code: code,
      market: config.market,
      result_rank: rank,
      query_length: raw.length,
    });
    if (symbol.data_status !== "ready") {
      if (config.market !== "US") return;
      setPreparingCode(code);
      setPreparationMessage("Preparing research in the background...");
      try {
        const status = await api.prepareResearch(code);
        setResults((current) =>
          current.map((item) =>
            item.code === code ? { ...item, data_status: "onboarding" } : item,
          ),
        );
        if (status.status === "review_required") {
          setPreparingCode(null);
          setPreparationMessage("Research prepared; evidence review is pending.");
        } else if (status.status === "rejected") {
          setPreparingCode(null);
          setPreparationMessage(
            `Preparation stopped: ${status.failure_reasons.join(", ") || "quality gates failed"}.`,
          );
        }
      } catch (error) {
        setPreparingCode(null);
        setPreparationMessage(
          error instanceof ApiError && error.status === 401
            ? "Sign in to prepare an unlisted research ticker."
            : error instanceof Error
              ? error.message
              : "Research preparation is unavailable.",
        );
      }
      return;
    }
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
          if (e.key === "Enter" && results[0]) void go(results[0], 1);
          if (e.key === "Escape") setOpen(false);
        }}
        placeholder={`🔍 ${t(config.market === "US" ? "search.placeholder.us" : "search.placeholder")}`}
        className="w-full bg-card border border-border rounded-xl px-3 py-1.5 text-sm outline-none focus:border-accent"
      />
      {open && results.length > 0 && (
        <div className="absolute left-0 right-0 mt-1 bg-surface border border-border rounded-xl overflow-hidden z-50 shadow-lg">
          {results.map((s, index) => (
            <button
              key={s.code}
              onMouseDown={() => void go(s, index + 1)}
              className="w-full text-left px-3 py-2 hover:bg-card flex items-center gap-2"
            >
              <CompanyLogo code={s.code} size={22} />
              <span className="font-bold text-[13px] text-accent shrink-0">${s.code}</span>
              <span className="text-xs text-muted truncate" lang="bn">
                {s.name_en}
                {s.name_bn ? ` · ${s.name_bn}` : ""}
              </span>
              {s.data_status !== "ready" && (
                <span className="ml-auto shrink-0 text-[10px] font-medium text-warn">
                  {preparingCode === s.code || s.data_status === "onboarding"
                    ? preparingCode === s.code
                      ? "Preparing"
                      : "Review pending"
                    : s.data_status === "degraded"
                      ? "Retry research"
                      : "Prepare research"}
                </span>
              )}
            </button>
          ))}
          {preparationMessage && (
            <div className="border-t border-border px-3 py-2 text-[10px] leading-relaxed text-muted">
              {preparationMessage}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
