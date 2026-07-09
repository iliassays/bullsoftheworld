export interface MarketUiConfig {
  market: string;
  exchangeCode: string;
  currencyCode: string;
  currencySymbol: string;
  timezone: string;
  timezoneLabel: string;
  priceDecimals: number;
}

export const DSE_MARKET: MarketUiConfig = {
  market: "DSE",
  exchangeCode: "DSE",
  currencyCode: "BDT",
  currencySymbol: "৳",
  timezone: "Asia/Dhaka",
  timezoneLabel: "BDT",
  priceDecimals: 1,
};

export const US_MARKET: MarketUiConfig = {
  market: "US",
  exchangeCode: "US",
  currencyCode: "USD",
  currencySymbol: "$",
  timezone: "America/New_York",
  timezoneLabel: "ET",
  priceDecimals: 2,
};

export function marketUiFromConfig(config: {
  market: string;
  exchange_code: string;
  currency_code: string;
  currency_symbol: string;
  timezone: string;
  price_decimals: number;
}): MarketUiConfig {
  return {
    market: config.market,
    exchangeCode: config.exchange_code,
    currencyCode: config.currency_code,
    currencySymbol: config.currency_symbol,
    timezone: config.timezone,
    timezoneLabel: config.timezone === "America/New_York" ? "ET" : config.currency_code,
    priceDecimals: config.price_decimals,
  };
}

export function formatMoney(
  n: number,
  market: MarketUiConfig = DSE_MARKET,
  digits = market.priceDecimals,
) {
  return `${market.currencySymbol}${n.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`;
}

export function formatCurrencyMillions(n: number | null | undefined, market = DSE_MARKET) {
  if (n == null) return "—";
  if (market.market === "DSE") {
    return n >= 10
      ? `৳${(n / 10).toLocaleString(undefined, { maximumFractionDigits: n >= 100 ? 0 : 1 })}Cr`
      : `৳${(n * 10).toLocaleString(undefined, { maximumFractionDigits: n >= 1 ? 0 : 1 })}L`;
  }
  return n >= 1000
    ? `${market.currencySymbol}${(n / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 })}B`
    : `${market.currencySymbol}${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}M`;
}
