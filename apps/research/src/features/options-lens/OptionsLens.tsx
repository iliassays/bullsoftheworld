import { Activity, AlertTriangle, ExternalLink, Info, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { useResearchAuth } from "../../app/auth";
import { researchDeployment } from "../../app/deployment";
import { AppTooltip, Button, IconButton, SelectField, StatusBadge } from "../../design-system";
import type { OptionContract } from "./model";
import { useOptionChain } from "./useOptionChain";

function number(value: number | null, digits = 2): string {
  return value === null
    ? "—"
    : new Intl.NumberFormat("en-US", { maximumFractionDigits: digits }).format(value);
}

function timestamp(value: string | null): string {
  if (!value) return "time unavailable";
  return new Intl.DateTimeFormat("en-US", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(new Date(value));
}

interface StrikeRow {
  strike: number;
  call?: OptionContract;
  put?: OptionContract;
}

function chainRows(contracts: OptionContract[]): StrikeRow[] {
  const rows = new Map<number, StrikeRow>();
  contracts.forEach((contract) => {
    const row = rows.get(contract.strike) ?? { strike: contract.strike };
    row[contract.optionType] = contract;
    rows.set(contract.strike, row);
  });
  return [...rows.values()].sort((left, right) => left.strike - right.strike);
}

function QuoteCell({ contract }: { contract?: OptionContract }) {
  if (!contract) return <span className="option-chain__empty">—</span>;
  return (
    <span className={`option-chain__quote option-chain__quote--${contract.liquidity}`}>
      <strong>{number(contract.bid)} / {number(contract.ask)}</strong>
      <small>IV {number(contract.impliedVolatilityPct, 1)}% · OI {number(contract.openInterest, 0)}</small>
    </span>
  );
}

export function OptionsLens({ workspaceId, code }: { workspaceId: string; code: string }) {
  const { user } = useResearchAuth();
  const [expiration, setExpiration] = useState<string>();
  const enabled = researchDeployment.market === "US" && user?.role === "admin";
  const query = useOptionChain(workspaceId, code, expiration, enabled);

  useEffect(() => setExpiration(undefined), [code]);

  const rows = useMemo(
    () => chainRows(query.data?.contracts ?? []),
    [query.data?.contracts],
  );

  if (!enabled) return null;
  if (query.isLoading) {
    return (
      <section className="dossier-panel options-lens options-lens--loading" aria-label="Loading options lens">
        <header className="dossier-panel__header"><span><Activity size={15} /><strong>Options lens</strong></span><StatusBadge tone="violet">Owner preview</StatusBadge></header>
        <div className="options-lens__skeleton" />
      </section>
    );
  }
  if (query.isError || !query.data) {
    return (
      <section className="dossier-panel options-lens options-lens--unavailable">
        <header className="dossier-panel__header"><span><Activity size={15} /><strong>Options lens</strong></span><StatusBadge tone="warning">Experimental</StatusBadge></header>
        <AlertTriangle aria-hidden="true" size={17} />
        <p>No usable listed chain is available from the preview source right now. The core dossier is unaffected.</p>
        <Button onPress={() => query.refetch()}><RefreshCw size={13} /> Retry source</Button>
      </section>
    );
  }

  const data = query.data;
  const metrics = data.metrics;
  const selectedExpiration = expiration ?? data.expiration;
  const qualityTone = metrics.quality === "usable" ? "positive" : "warning";
  const expiryOptions = data.availableExpirations.map((value) => ({ value, label: value }));

  return (
    <section className="dossier-panel options-lens">
      <header className="dossier-panel__header options-lens__header">
        <span><Activity aria-hidden="true" size={15} /><strong>Options lens</strong></span>
        <span className="options-lens__actions">
          <StatusBadge tone={qualityTone} dot>{metrics.quality.replace(/_/g, " ")}</StatusBadge>
          <IconButton label="Refresh option chain" onPress={() => query.refetch()}><RefreshCw size={13} /></IconButton>
        </span>
      </header>
      <div className="options-lens__source-row">
        <span>Expiry</span>
        {expiryOptions.length > 0 && (
          <SelectField label="Option expiration" value={selectedExpiration} options={expiryOptions} onChange={setExpiration} />
        )}
        <small>Underlying {number(data.underlyingPrice)} · {timestamp(data.underlyingAsOf)}</small>
      </div>
      <p className="dossier-interpretation options-lens__summary">{data.summary}</p>
      <div className="options-lens__metrics">
        <div><span>P/C open interest <AppTooltip label="Put open interest divided by call open interest for this expiry. It is not a directional signal."><Info aria-label="Put-call open interest definition" size={11} /></AppTooltip></span><strong>{number(metrics.putCallOpenInterestRatio)}</strong></div>
        <div><span>ATM implied vol.</span><strong>{number(metrics.atmImpliedVolatilityPct, 1)}%</strong></div>
        <div><span>Implied move <AppTooltip label="Nearest same-strike call plus put midpoint, divided by the underlying price. Approximate and expiry-specific."><Info aria-label="Implied move definition" size={11} /></AppTooltip></span><strong>{number(metrics.impliedMovePct, 1)}%</strong></div>
        <div><span>Downside skew <AppTooltip label="Approximate downside put IV minus upside call IV. Positive values mean downside contracts are priced with higher volatility."><Info aria-label="Downside skew definition" size={11} /></AppTooltip></span><strong>{metrics.approximateDownsideSkewPp === null ? "—" : `${metrics.approximateDownsideSkewPp > 0 ? "+" : ""}${number(metrics.approximateDownsideSkewPp, 1)} pp`}</strong></div>
      </div>
      <div className="options-lens__coverage">
        <span><strong>{metrics.liquidContractCount}</strong> liquid of {metrics.contractCount} contracts</span>
        <span><strong>{number(metrics.twoSidedQuotePct, 1)}%</strong> two-sided quote coverage</span>
      </div>
      <div className="option-chain" role="region" aria-label={`${code} option chain for ${data.expiration}`} tabIndex={0}>
        <div className="option-chain__head"><span>Call bid / ask</span><strong>Strike</strong><span>Put bid / ask</span></div>
        {rows.map((row) => (
          <div className={Math.abs(row.strike - data.underlyingPrice) <= data.underlyingPrice * 0.025 ? "option-chain__row option-chain__row--atm" : "option-chain__row"} key={row.strike}>
            <QuoteCell contract={row.call} />
            <strong className="tnum">{number(row.strike)}</strong>
            <QuoteCell contract={row.put} />
          </div>
        ))}
      </div>
      <footer className="options-lens__footer">
        <span>Delayed experimental source · fetched {timestamp(data.fetchedAt)}</span>
        <a href={data.sourceUrl} rel="noreferrer" target="_blank">Open source <ExternalLink size={11} /></a>
      </footer>
      <details className="dossier-limitations">
        <summary>Method and licensing limitations</summary>
        <ul>{data.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
      </details>
    </section>
  );
}
