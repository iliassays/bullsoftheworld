import type { OptionChainPreview } from "./model";

export function previewOptionChain(workspaceId: string, code: string): OptionChainPreview {
  const expiration = "2026-08-21";
  const strikes = [42.5, 45, 47.5, 50, 52.5, 55, 57.5];
  const contracts = strikes.flatMap((strike) =>
    (["call", "put"] as const).map((optionType) => ({
      contractSymbol: `${code}260821${optionType === "call" ? "C" : "P"}${String(strike * 1000).padStart(8, "0")}`,
      optionType,
      expiration,
      strike,
      currency: "USD",
      lastPrice: 3.1,
      bid: 2.95,
      ask: 3.25,
      midpoint: 3.1,
      spreadPct: 9.68,
      volume: optionType === "call" ? 184 : 126,
      openInterest: optionType === "call" ? 1120 : 980,
      impliedVolatilityPct: optionType === "call" ? 61.4 : 66.8,
      inTheMoney: optionType === "call" ? strike < 51.2 : strike > 51.2,
      lastTradeAt: "2026-07-17T19:55:00Z",
      liquidity: "usable" as const,
    })),
  );
  return {
    tenantId: "bullsofwallst",
    market: "US",
    workspaceId,
    code: code.toUpperCase(),
    expiration,
    availableExpirations: [expiration, "2026-09-18", "2026-10-16"],
    underlyingPrice: 51.2,
    underlyingAsOf: "2026-07-17T20:00:00Z",
    marketState: "CLOSED",
    fetchedAt: "2026-07-17T20:02:00Z",
    currency: "USD",
    provider: "yahoo_unofficial",
    sourceUrl: `https://finance.yahoo.com/quote/${code}/options`,
    isDelayed: true,
    experimental: true,
    accessScope: "platform_admin",
    summary:
      "Usable two-sided quotes cover 92.4% of returned contracts. Put/call open-interest ratio is 0.88. These measurements describe the observed chain; they do not identify trade direction or predict return.",
    metrics: {
      quality: "usable",
      contractCount: contracts.length,
      displayedContractCount: contracts.length,
      liquidContractCount: 12,
      twoSidedQuotePct: 92.4,
      callVolume: 1288,
      putVolume: 882,
      putCallVolumeRatio: 0.685,
      callOpenInterest: 7840,
      putOpenInterest: 6860,
      putCallOpenInterestRatio: 0.875,
      atmImpliedVolatilityPct: 64.1,
      approximateDownsideSkewPp: 5.4,
      impliedMovePct: 12.1,
    },
    contracts,
    limitations: [
      "Experimental owner preview from an unofficial, unlicensed source; not approved for public redistribution.",
      "Quotes may be delayed, stale, incomplete, or absent. Atlas does not infer missing values.",
      "Volume and open interest do not reveal whether a contract was bought or sold, opened or closed.",
      "Greeks and historical volatility surfaces are unavailable in this preview and are not estimated.",
    ],
  };
}
