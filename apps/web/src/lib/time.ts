const DSE_TIME_ZONE = "Asia/Dhaka";

type DateInput = string | number | Date | null | undefined;

function toDate(value: DateInput): Date | null {
  if (value == null) return null;
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

const dhakaDateTime = new Intl.DateTimeFormat("en-GB", {
  timeZone: DSE_TIME_ZONE,
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

const dhakaTime = new Intl.DateTimeFormat("en-GB", {
  timeZone: DSE_TIME_ZONE,
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

export function formatDhakaDateTime(value: DateInput): string {
  const date = toDate(value);
  return date ? `${dhakaDateTime.format(date)} BDT` : "—";
}

export function formatDhakaTime(value: DateInput): string {
  const date = toDate(value);
  return date ? `${dhakaTime.format(date)} BDT` : "—";
}
