import { DSE_MARKET, type MarketUiConfig } from "./market";

type DateInput = string | number | Date | null | undefined;

function toDate(value: DateInput): Date | null {
  if (value == null) return null;
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function dateTimeFormatter(market: MarketUiConfig) {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: market.timezone,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function timeFormatter(market: MarketUiConfig) {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: market.timezone,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

const dhakaDateTime = new Intl.DateTimeFormat("en-GB", {
  timeZone: DSE_MARKET.timezone,
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

const dhakaTime = new Intl.DateTimeFormat("en-GB", {
  timeZone: DSE_MARKET.timezone,
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

export function formatMarketDateTime(value: DateInput, market: MarketUiConfig = DSE_MARKET): string {
  const date = toDate(value);
  return date ? `${dateTimeFormatter(market).format(date)} ${market.timezoneLabel}` : "—";
}

export function formatMarketTime(value: DateInput, market: MarketUiConfig = DSE_MARKET): string {
  const date = toDate(value);
  return date ? `${timeFormatter(market).format(date)} ${market.timezoneLabel}` : "—";
}

export function formatDhakaDateTime(value: DateInput): string {
  const date = toDate(value);
  return date ? `${dhakaDateTime.format(date)} ${DSE_MARKET.timezoneLabel}` : "—";
}

export function formatDhakaTime(value: DateInput): string {
  const date = toDate(value);
  return date ? `${dhakaTime.format(date)} ${DSE_MARKET.timezoneLabel}` : "—";
}
