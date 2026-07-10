import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, type MarketConfig } from "./api";
import { marketUiFromConfig, setActiveMarket } from "./market";

const DSE_FALLBACK: MarketConfig = {
  market: "DSE",
  exchange_code: "DSE",
  exchange_label_bn: "ডিএসই",
  exchange_name: "Dhaka Stock Exchange",
  exchange_name_bn: "ঢাকা স্টক এক্সচেঞ্জ",
  country_code: "BD",
  currency_code: "BDT",
  currency_symbol: "৳",
  timezone: "Asia/Dhaka",
  timezone_label: "BDT",
  place_label_en: "Dhaka",
  place_label_bn: "ঢাকা",
  open_time: "10:00",
  close_time: "14:30",
  settlement_cycle: "T+2",
  benchmark_label: "DSEX",
  default_locale: "bn",
  price_decimals: 1,
  compact_money_units: [
    { min_value_mn: 10, divisor_mn: 10, suffix: "cr", decimals: 1 },
    { min_value_mn: 0, divisor_mn: 0.1, suffix: "L", decimals: 0 },
  ],
  market_cap_money_units: [{ min_value_mn: 0, divisor_mn: 10, suffix: " Cr", decimals: 0 }],
  features: {
    intraday_quotes: true,
    curated_screens: true,
    official_disclosures: true,
    company_fundamentals: true,
    automated_desks: true,
    learning_quiz: true,
    interpreted_analytics: true,
    price_alerts: true,
    dse_categories: true,
    circuit_breakers: true,
    shareholding_breakdown: true,
    sponsor_director_disclosures: true,
    block_trades: true,
    sec_filings: false,
    extended_hours: false,
  },
  tenant_name: "bullsofdhaka",
  brand_name: "Bulls of Dhaka",
  site_url: "https://bullsofdhaka.com",
  support_email: "hello@bullsofdhaka.com",
  logo_url: "https://bullsofdhaka.com/logo-mark-v2.png",
  tagline_en: "Facts, not rumours",
  tagline_bn: "তথ্যে চলুন, গুজবে নয়",
  social_url: "https://www.facebook.com/1214682241723822",
};

const US_FALLBACK: MarketConfig = {
  ...DSE_FALLBACK,
  market: "US",
  exchange_code: "US",
  exchange_label_bn: "যুক্তরাষ্ট্রের শেয়ারবাজার",
  exchange_name: "U.S. equities",
  exchange_name_bn: "যুক্তরাষ্ট্রের শেয়ারবাজার",
  country_code: "US",
  currency_code: "USD",
  currency_symbol: "$",
  timezone: "America/New_York",
  timezone_label: "ET",
  place_label_en: "New York",
  place_label_bn: "নিউ ইয়র্ক",
  open_time: "09:30",
  close_time: "16:00",
  settlement_cycle: "T+1",
  benchmark_label: "S&P 500",
  default_locale: "en",
  price_decimals: 2,
  compact_money_units: [
    { min_value_mn: 1000, divisor_mn: 1000, suffix: "B", decimals: 1 },
    { min_value_mn: 0, divisor_mn: 1, suffix: "M", decimals: 1 },
  ],
  market_cap_money_units: [
    { min_value_mn: 1000, divisor_mn: 1000, suffix: "B", decimals: 1 },
    { min_value_mn: 0, divisor_mn: 1, suffix: "M", decimals: 0 },
  ],
  features: { interpreted_analytics: true },
  tenant_name: "bullsofwallst",
  brand_name: "Bulls of Wall Street",
  site_url: "https://bullsofwallst.com",
  support_email: "hello@bullsofwallst.com",
  logo_url: "https://bullsofwallst.com/logo-mark-v2.png",
  tagline_en: "US market intelligence, not noise",
  tagline_bn: "যুক্তরাষ্ট্রের বাজার তথ্য, গুজব নয়",
  social_url: null,
};

function fallbackConfig(): MarketConfig {
  if (typeof window !== "undefined" && window.location.hostname.includes("bullsofwallst")) {
    return US_FALLBACK;
  }
  return DSE_FALLBACK;
}

function siteOrigin(): string {
  if (typeof window === "undefined") return "https://bullsofdhaka.com";
  return window.location.origin;
}

interface TenantContextValue {
  config: MarketConfig;
  siteUrl: string;
}

const TenantContext = createContext<TenantContextValue>({
  config: DSE_FALLBACK,
  siteUrl: "https://bullsofdhaka.com",
});

export function TenantConfigProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<MarketConfig>(() => {
    const initial = fallbackConfig();
    setActiveMarket(marketUiFromConfig(initial));
    return initial;
  });
  const siteUrl = useMemo(() => siteOrigin(), []);

  useEffect(() => {
    let live = true;
    api
      .marketConfig()
      .then((next) => {
        if (live) {
          setActiveMarket(marketUiFromConfig(next));
          setConfig(next);
        }
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, []);

  return <TenantContext.Provider value={{ config, siteUrl }}>{children}</TenantContext.Provider>;
}

export function useTenantConfig(): TenantContextValue {
  return useContext(TenantContext);
}
