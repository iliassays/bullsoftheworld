import { useEffect, useRef, useState } from "react";
import { useLang } from "../lib/i18n";
import { useNavigate } from "../lib/nav";
import { ApiError, api, type DeskSearchResult, type SymbolOut } from "../lib/api";
import { DeskIcon, hasDeskIcon } from "../lib/deskIcons";
import { chooseSearchTarget } from "../lib/search-target";
import { searchSymbols } from "../lib/symbols";
import { useTenantConfig } from "../lib/tenant";
import { trackProductEvent } from "../lib/analytics";
import { CompanyLogo } from "./CompanyLogo";
import { VerifiedBadge } from "./ui";

const canOpenResearch = (status: SymbolOut["data_status"]) =>
  status === "ready" || status === "research_only";

function searchStatusLabel(symbol: SymbolOut, preparingCode: string | null): string | null {
  if (symbol.data_status === "ready") return null;
  if (symbol.data_status === "research_only") return "High risk";
  if (preparingCode === symbol.code || symbol.data_status === "onboarding") return "Preparing";
  if (symbol.data_status === "degraded") return "Retry research";
  return "Prepare research";
}

export function SearchBar() {
  const { t } = useLang();
  const { config } = useTenantConfig();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<SymbolOut[]>([]);
  const [agents, setAgents] = useState<DeskSearchResult[]>([]);
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
      setAgents([]);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      Promise.all([
        searchSymbols(raw, 6),
        config.features.automated_desks
          ? api.searchDesks(raw, 4).catch(() => [])
          : Promise.resolve([]),
      ]).then(([symbols, matchingAgents]) => {
        if (cancelled) return;
        setResults(symbols);
        setAgents(matchingAgents);
      });
    }, 120);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [config.features.automated_desks, open, raw]);

  useEffect(() => {
    if (!preparingCode) return;
    const poll = window.setInterval(() => {
      api
        .researchPreparation(preparingCode)
        .then((status) => {
          if (status.can_open) {
            window.clearInterval(poll);
            setPreparingCode(null);
            navigate(`/s/${status.code}`);
          } else if (["review_required", "rejected", "failed"].includes(status.status)) {
            window.clearInterval(poll);
            setPreparingCode(null);
            setPreparationMessage(
              status.status === "rejected"
                ? `Preparation stopped: ${status.failure_reasons.join(", ") || "quality gates failed"}.`
                : "Preparation could not finish and can be retried.",
            );
          }
        })
        .catch(() => undefined);
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
    if (!canOpenResearch(symbol.data_status)) {
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
        if (status.can_open) {
          setPreparingCode(null);
          setQ("");
          setOpen(false);
          navigate(`/s/${status.code}`);
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

  const goAgent = (agent: DeskSearchResult, rank = 1) => {
    trackProductEvent("select_search_result", {
      market: config.market,
      result_rank: rank,
      query_length: raw.length,
      surface: "agent",
      destination: "desk_profile",
    });
    setQ("");
    setOpen(false);
    navigate(`/desk/${encodeURIComponent(agent.handle)}`);
  };

  const chooseFirstResult = () => {
    const target = chooseSearchTarget(raw, results, agents);
    if (!target) return;
    if (target.kind === "symbol") {
      void go(target.value, results.indexOf(target.value) + 1);
      return;
    }
    goAgent(target.value, results.length + agents.indexOf(target.value) + 1);
  };

  const hasResults = results.length > 0 || agents.length > 0;

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
          if (e.key === "Enter") chooseFirstResult();
          if (e.key === "Escape") setOpen(false);
        }}
        placeholder={`🔍 ${t(config.market === "US" ? "search.placeholder.us" : "search.placeholder")}`}
        aria-label={t("search.ariaLabel")}
        aria-autocomplete="list"
        aria-expanded={open && hasResults}
        aria-controls="global-search-results"
        className="w-full bg-card border border-border rounded-xl px-3 py-1.5 text-sm outline-none focus:border-accent"
      />
      {open && hasResults && (
        <div
          id="global-search-results"
          role="listbox"
          className="absolute left-0 right-0 mt-1 bg-surface border border-border rounded-xl overflow-hidden z-50 shadow-lg"
        >
          {results.length > 0 && (
            <div className="border-b border-border/70 bg-card/60 px-3 py-1 text-[9px] font-semibold uppercase tracking-wide text-muted">
              {t("search.stocks")}
            </div>
          )}
          {results.map((s, index) => (
            <button
              key={`symbol:${s.code}`}
              type="button"
              role="option"
              onMouseDown={(event) => {
                event.preventDefault();
                void go(s, index + 1);
              }}
              className="w-full cursor-pointer text-left px-3 py-2 hover:bg-card flex items-center gap-2"
            >
              <CompanyLogo code={s.code} size={22} />
              <span className="font-bold text-[13px] text-accent shrink-0">${s.code}</span>
              <span className="text-xs text-muted truncate" lang="bn">
                {s.name_en}
                {s.name_bn ? ` · ${s.name_bn}` : ""}
              </span>
              {searchStatusLabel(s, preparingCode) && (
                <span className="ml-auto shrink-0 text-[10px] font-medium text-warn">
                  {searchStatusLabel(s, preparingCode)}
                </span>
              )}
            </button>
          ))}
          {agents.length > 0 && (
            <div className="border-y border-border/70 bg-card/60 px-3 py-1 text-[9px] font-semibold uppercase tracking-wide text-muted">
              {t("search.agents")}
            </div>
          )}
          {agents.map((agent, index) => {
            const initials = agent.name
              .split(/\s+/)
              .map((part) => part[0])
              .slice(0, 2)
              .join("")
              .toUpperCase();
            return (
              <button
                key={`agent:${agent.handle}`}
                type="button"
                role="option"
                onMouseDown={(event) => {
                  event.preventDefault();
                  goAgent(agent, results.length + index + 1);
                }}
                className="w-full cursor-pointer text-left px-3 py-2 hover:bg-card flex items-center gap-2.5"
              >
                <span className="h-[26px] w-[26px] shrink-0 rounded-full border border-accent/40 bg-card text-accent grid place-items-center text-[9px] font-bold">
                  {hasDeskIcon(agent.handle) ? (
                    <DeskIcon handle={agent.handle} size={15} />
                  ) : (
                    initials
                  )}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1 text-[13px] font-semibold text-text">
                    <span className="truncate">{agent.name}</span>
                    {agent.verified && <VerifiedBadge size={13} />}
                  </span>
                  <span className="block truncate text-[10px] text-muted">
                    @{agent.handle} · {t("search.officialAgent")}
                  </span>
                </span>
              </button>
            );
          })}
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
