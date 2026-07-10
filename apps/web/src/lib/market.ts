export interface MoneyUnit {
  minValueMn: number;
  divisorMn: number;
  suffix: string;
  decimals: number;
}

export interface MarketUiConfig {
  market: string;
  exchangeCode: string;
  currencyCode: string;
  currencySymbol: string;
  timezone: string;
  timezoneLabel: string;
  priceDecimals: number;
  compactMoneyUnits: MoneyUnit[];
  marketCapMoneyUnits: MoneyUnit[];
}

export const DSE_MARKET: MarketUiConfig = {
  market: "DSE",
  exchangeCode: "DSE",
  currencyCode: "BDT",
  currencySymbol: "৳",
  timezone: "Asia/Dhaka",
  timezoneLabel: "BDT",
  priceDecimals: 1,
  compactMoneyUnits: [
    { minValueMn: 10, divisorMn: 10, suffix: "cr", decimals: 1 },
    { minValueMn: 0, divisorMn: 0.1, suffix: "L", decimals: 0 },
  ],
  marketCapMoneyUnits: [{ minValueMn: 0, divisorMn: 10, suffix: " Cr", decimals: 0 }],
};

export const US_MARKET: MarketUiConfig = {
  market: "US",
  exchangeCode: "US",
  currencyCode: "USD",
  currencySymbol: "$",
  timezone: "America/New_York",
  timezoneLabel: "ET",
  priceDecimals: 2,
  compactMoneyUnits: [
    { minValueMn: 1000, divisorMn: 1000, suffix: "B", decimals: 1 },
    { minValueMn: 0, divisorMn: 1, suffix: "M", decimals: 1 },
  ],
  marketCapMoneyUnits: [
    { minValueMn: 1000, divisorMn: 1000, suffix: "B", decimals: 1 },
    { minValueMn: 0, divisorMn: 1, suffix: "M", decimals: 0 },
  ],
};

// One browser session serves one tenant. Components can use the compact formatting helpers without
// threading market metadata through every leaf; the tenant provider sets this before children render.
let activeMarket: MarketUiConfig = DSE_MARKET;

export function setActiveMarket(market: MarketUiConfig): void {
  activeMarket = market;
}

export function marketUiFromConfig(config: {
  market: string;
  exchange_code: string;
  currency_code: string;
  currency_symbol: string;
  timezone: string;
  timezone_label: string;
  price_decimals: number;
  compact_money_units: Array<{
    min_value_mn: number;
    divisor_mn: number;
    suffix: string;
    decimals: number;
  }>;
  market_cap_money_units: Array<{
    min_value_mn: number;
    divisor_mn: number;
    suffix: string;
    decimals: number;
  }>;
}): MarketUiConfig {
  const convertUnit = (unit: {
    min_value_mn: number;
    divisor_mn: number;
    suffix: string;
    decimals: number;
  }): MoneyUnit => ({
    minValueMn: unit.min_value_mn,
    divisorMn: unit.divisor_mn,
    suffix: unit.suffix,
    decimals: unit.decimals,
  });
  return {
    market: config.market,
    exchangeCode: config.exchange_code,
    currencyCode: config.currency_code,
    currencySymbol: config.currency_symbol,
    timezone: config.timezone,
    timezoneLabel: config.timezone_label,
    priceDecimals: config.price_decimals,
    compactMoneyUnits: config.compact_money_units.map(convertUnit),
    marketCapMoneyUnits: config.market_cap_money_units.map(convertUnit),
  };
}

export function formatMoney(
  n: number,
  market: MarketUiConfig = activeMarket,
  digits = market.priceDecimals,
) {
  return `${market.currencySymbol}${n.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`;
}

export function formatCurrencyMillions(n: number | null | undefined, market = activeMarket) {
  if (n == null) return "—";
  const units = market.compactMoneyUnits.length ? market.compactMoneyUnits : activeMarket.compactMoneyUnits;
  const unit = units.find((candidate) => n >= candidate.minValueMn) ?? units[units.length - 1];
  return `${market.currencySymbol}${(n / unit.divisorMn).toLocaleString(undefined, {
    minimumFractionDigits: unit.decimals,
    maximumFractionDigits: unit.decimals,
  })}${unit.suffix}`;
}
