export type OptionLiquidity = "usable" | "thin" | "unquoted";

export interface OptionContract {
  contractSymbol: string;
  optionType: "call" | "put";
  expiration: string;
  strike: number;
  currency: string;
  lastPrice: number | null;
  bid: number | null;
  ask: number | null;
  midpoint: number | null;
  spreadPct: number | null;
  volume: number | null;
  openInterest: number | null;
  impliedVolatilityPct: number | null;
  inTheMoney: boolean;
  lastTradeAt: string | null;
  liquidity: OptionLiquidity;
}

export interface OptionChainPreview {
  tenantId: string;
  market: "US";
  workspaceId: string;
  code: string;
  expiration: string;
  availableExpirations: string[];
  underlyingPrice: number;
  underlyingAsOf: string | null;
  marketState: string | null;
  fetchedAt: string;
  currency: string;
  provider: string;
  sourceUrl: string;
  isDelayed: boolean;
  experimental: true;
  accessScope: "platform_admin";
  summary: string;
  metrics: {
    quality: "usable" | "thin" | "no_liquid_options";
    contractCount: number;
    displayedContractCount: number;
    liquidContractCount: number;
    twoSidedQuotePct: number;
    callVolume: number;
    putVolume: number;
    putCallVolumeRatio: number | null;
    callOpenInterest: number;
    putOpenInterest: number;
    putCallOpenInterestRatio: number | null;
    atmImpliedVolatilityPct: number | null;
    approximateDownsideSkewPp: number | null;
    impliedMovePct: number | null;
  };
  contracts: OptionContract[];
  limitations: string[];
}
