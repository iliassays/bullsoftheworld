import { FileSearch, Search } from "lucide-react";
import { useDeferredValue, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { StatusBadge } from "../../design-system";
import { useResearchQueue, useResearchWorkspaces } from "../research-queue/useResearchQueue";

export function CompanyDossierLibraryPage() {
  const workspaces = useResearchWorkspaces();
  const workspace = workspaces.data?.[0];
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const queue = useResearchQueue(workspace?.id, { query: deferredQuery });
  const candidates = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return (queue.data?.candidates ?? []).filter((candidate) =>
      !normalized
        ? true
        : `${candidate.ticker} ${candidate.company} ${candidate.sector}`.toLowerCase().includes(normalized),
    );
  }, [query, queue.data?.candidates]);

  if (workspaces.isLoading || queue.isLoading) {
    return <div aria-label="Loading company dossiers" className="dossier-loading" />;
  }

  return (
    <div className="dossier-library-page">
      <header className="queue-page-header">
        <div>
          <span className="queue-page-header__eyebrow">Evidence-bound company research</span>
          <h1>Company dossiers</h1>
          <p>Open a point-in-time company record assembled from the current tenant's official evidence and market data.</p>
        </div>
      </header>
      <label className="dossier-library-search">
        <Search aria-hidden="true" size={16} />
        <input
          aria-label="Search company dossiers"
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search ticker, company, or sector"
          value={query}
        />
      </label>
      <div className="dossier-library-list">
        {candidates.map((candidate) => (
          <Link key={candidate.id} to={`/companies/${encodeURIComponent(candidate.ticker)}`}>
            <span className={`queue-security__market queue-security__market--${candidate.market.toLowerCase()}`}>{candidate.market}</span>
            <span className="dossier-library-list__identity"><strong>{candidate.ticker}</strong><small>{candidate.company} · {candidate.sector}</small></span>
            <StatusBadge tone={candidate.evidence.freshness === "fresh" ? "positive" : candidate.evidence.freshness === "aging" ? "warning" : "negative"} dot>{candidate.evidence.freshness}</StatusBadge>
            <span className="dossier-library-list__priority"><small>Urgency</small><strong className="tnum">{candidate.priority}</strong></span>
          </Link>
        ))}
        {candidates.length === 0 && (
          <div className="queue-empty"><FileSearch aria-hidden="true" size={22} /><strong>No dossier matches this search</strong><span>Use a ticker, issuer name, or sector.</span></div>
        )}
      </div>
    </div>
  );
}
