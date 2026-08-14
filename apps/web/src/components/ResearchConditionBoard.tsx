import { useEffect, useMemo, useState } from "react";

import {
  api,
  type PublicConditionBoard as PublicConditionBoardData,
  type PublicConditionGroup,
  type PublicConditionItem,
  type PublicConditionKey,
} from "../lib/api";
import { useLang, type Lang } from "../lib/i18n";
import { formatCurrencyMillions, formatMoney } from "../lib/market";
import { Link } from "../lib/nav";
import { buildAtlasConditionUrl, hasLaterConditionClose } from "../lib/research-conditions";
import { useTenantConfig } from "../lib/tenant";
import { CompanyLogo } from "./CompanyLogo";
import { Spinner } from "./ui";

const CONDITION_ORDER: PublicConditionKey[] = [
  "trend_alignment",
  "participation_expansion",
  "controlled_pullback_context",
];

const CONDITION_COPY: Record<PublicConditionKey, Record<Lang, { label: string; summary: string }>> = {
  trend_alignment: {
    en: {
      label: "Trend alignment",
      summary: "Price and the 20/50-session trend are moving in the same direction.",
    },
    bn: {
      label: "ট্রেন্ডের সামঞ্জস্য",
      summary: "দাম ও ২০/৫০ সেশনের ট্রেন্ড একই দিকে এগোচ্ছে।",
    },
  },
  participation_expansion: {
    en: {
      label: "Participation",
      summary: "A positive completed session arrived with volume above its recent pace.",
    },
    bn: {
      label: "লেনদেনে অংশগ্রহণ",
      summary: "পজিটিভ সমাপ্ত সেশনে সাম্প্রতিক গতির চেয়ে বেশি ভলিউম ছিল।",
    },
  },
  controlled_pullback_context: {
    en: {
      label: "Controlled pullback",
      summary: "The larger trend remains intact while price pauses near its shorter trend.",
    },
    bn: {
      label: "নিয়ন্ত্রিত পুলব্যাক",
      summary: "বড় ট্রেন্ড অক্ষুণ্ণ রেখে দাম স্বল্পমেয়াদি ট্রেন্ডের কাছে বিরতি নিয়েছে।",
    },
  },
};

const CAP_LABELS: Record<string, Record<Lang, string>> = {
  mega: { en: "Mega cap", bn: "মেগা ক্যাপ" },
  large: { en: "Large cap", bn: "লার্জ ক্যাপ" },
  mid: { en: "Mid cap", bn: "মিড ক্যাপ" },
  small: { en: "Small cap", bn: "স্মল ক্যাপ" },
  micro: { en: "Micro cap", bn: "মাইক্রো ক্যাপ" },
  unclassified: { en: "Unclassified", bn: "শ্রেণিবিহীন" },
};

function formatDate(value: string | null, lang: Lang): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat(lang === "bn" ? "bn-BD" : "en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T12:00:00Z`));
}

function signedPercent(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function ConditionRow({ item, condition }: { item: PublicConditionItem; condition: PublicConditionKey }) {
  const { lang } = useLang();
  const hasLaterClose = hasLaterConditionClose(item.observed_on, item.latest_session_date);
  const returnTone = item.close_return_since_observation_pct < 0 ? "text-down" : "text-up";
  const evidenceLabel = item.evidence_mode === "forward"
    ? (lang === "bn" ? "সামনে থেকে রেকর্ড" : "Recorded forward")
    : (lang === "bn" ? "ইতিহাস থেকে পুনর্গঠন" : "Historical reconstruction");

  return (
    <Link
      to={`/s/${item.code}?condition=${condition}`}
      className="grid cursor-pointer grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 border-t border-border py-3 first:border-t-0 hover:bg-card/40"
    >
      <CompanyLogo code={item.code} size={32} />
      <span className="min-w-0">
        <span className="flex min-w-0 flex-wrap items-center gap-1.5">
          <strong className="text-sm text-text">${item.code}</strong>
          {item.is_new && (
            <span className="rounded-md border border-up/40 bg-up/10 px-1.5 py-0.5 text-[9px] font-bold uppercase text-up">
              {lang === "bn" ? "নতুন" : "New"}
            </span>
          )}
          <span className="rounded-md border border-border bg-card px-1.5 py-0.5 text-[9px] font-semibold text-muted">
            {evidenceLabel}
          </span>
        </span>
        <span className="mt-0.5 block truncate text-[11px] text-muted">{item.name}</span>
        <span className="mt-1 block text-[10px] text-muted">
          {CAP_LABELS[item.cap_tier]?.[lang] ?? item.cap_tier}
          {item.average_daily_value_mn !== null
            ? ` · ${formatCurrencyMillions(item.average_daily_value_mn)} ${lang === "bn" ? "গড় দৈনিক" : "avg daily"}`
            : ""}
        </span>
      </span>
      <span className="shrink-0 text-right tnum">
        <strong className="block text-[13px] text-text">{formatMoney(item.latest_close)}</strong>
        {hasLaterClose ? (
          <span className={`block text-xs font-semibold ${returnTone}`}>
            {signedPercent(item.close_return_since_observation_pct)}
          </span>
        ) : (
          <span className="block text-[10px] text-muted">{lang === "bn" ? "পরের ক্লোজ বাকি" : "Next close pending"}</span>
        )}
        <span className="mt-0.5 block text-[9px] text-muted">
          {lang === "bn" ? "দেখা" : "observed"} {formatDate(item.observed_on, lang)}
        </span>
      </span>
    </Link>
  );
}

export function ResearchConditionBoard({ size }: { size?: string }) {
  const { lang } = useLang();
  const { config } = useTenantConfig();
  const [data, setData] = useState<PublicConditionBoardData | null | undefined>();
  const [selectedKey, setSelectedKey] = useState<PublicConditionKey>("trend_alignment");
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let live = true;
    setData(undefined);
    api.researchConditions(5, size)
      .then((response) => live && setData(response))
      .catch(() => live && setData(null));
    return () => { live = false; };
  }, [reload, size]);

  const groups = useMemo(
    () => CONDITION_ORDER.map((key) => data?.groups.find((group) => group.key === key)).filter(
      (group): group is PublicConditionGroup => Boolean(group),
    ),
    [data],
  );
  const selected = groups.find((group) => group.key === selectedKey) ?? groups[0];

  if (data === undefined) return <Spinner />;
  if (data === null) {
    return (
      <section className="rounded-2xl border border-border bg-surface p-4 text-center">
        <strong className="text-sm">{lang === "bn" ? "গবেষণার শর্ত এখন পাওয়া যাচ্ছে না" : "Research conditions are unavailable"}</strong>
        <button className="mt-2 block w-full cursor-pointer text-xs font-semibold text-accent" onClick={() => setReload((value) => value + 1)} type="button">
          {lang === "bn" ? "আবার চেষ্টা করুন" : "Retry"}
        </button>
      </section>
    );
  }
  if (!selected) return null;

  const copy = CONDITION_COPY[selected.key][lang];
  const atlasUrl = buildAtlasConditionUrl(config.research_site_url, selected.key, size);
  const containsReplay = selected.items.some((item) => item.evidence_mode === "reconstructed");

  return (
    <section className="overflow-hidden rounded-2xl border border-border bg-surface">
      <header className="border-b border-border px-4 py-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wide text-accent">
              {lang === "bn" ? "সম্পূর্ণ সেশনের পর্যবেক্ষণ" : "Completed-session observations"}
            </p>
            <h2 className="mt-0.5 text-base font-bold text-text">
              {lang === "bn" ? "গবেষণার শর্ত" : "Research conditions"}
            </h2>
          </div>
          <span className="text-[10px] text-muted">
            {lang === "bn" ? "তথ্য" : "Through"} {formatDate(data.as_of_date, lang)}
          </span>
        </div>
        <p className="mt-1 text-xs leading-relaxed text-muted">
          {lang === "bn"
            ? "কোন শেয়ারে নিবন্ধিত বাজার-শর্ত এখন মিলছে—গভীর গবেষণার শুরু, ট্রেড তালিকা নয়।"
            : "Where registered market conditions are currently present—a starting point for research, not a trade list."}
        </p>
      </header>

      <div className="flex gap-1 overflow-x-auto border-b border-border px-3 py-2" role="tablist">
        {groups.map((group) => (
          <button
            aria-selected={selected.key === group.key}
            className={`min-w-fit cursor-pointer rounded-md border px-2.5 py-1.5 text-[11px] font-semibold ${
              selected.key === group.key
                ? "border-accent bg-accent/10 text-text"
                : "border-border bg-card text-muted hover:text-text"
            }`}
            key={group.key}
            onClick={() => setSelectedKey(group.key)}
            role="tab"
            type="button"
          >
            {CONDITION_COPY[group.key][lang].label} · {group.observed_count}
            {group.new_count > 0 ? ` (${group.new_count} ${lang === "bn" ? "নতুন" : "new"})` : ""}
          </button>
        ))}
      </div>

      <div className="px-4 py-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-text">{copy.label}</h3>
            <p className="mt-0.5 text-xs leading-relaxed text-muted">{copy.summary}</p>
          </div>
          <a className="shrink-0 text-[11px] font-semibold text-accent hover:underline" href={atlasUrl}>
            {lang === "bn" ? "Atlas-এ সব দেখুন ↗" : "Open full Atlas scanner ↗"}
          </a>
        </div>

        <div className="mt-2">
          {selected.items.map((item) => (
            <ConditionRow condition={selected.key} item={item} key={item.code} />
          ))}
          {!selected.items.length && (
            <div className="border-t border-border py-6 text-center text-xs text-muted">
              {lang === "bn"
                ? "এই আকারে সর্বশেষ ক্লোজে কোনো শেয়ার সম্পূর্ণ শর্ত পূরণ করেনি।"
                : "No security in this size meets the complete condition at the latest close."}
            </div>
          )}
        </div>
      </div>

      <footer className="border-t border-border bg-card/30 px-4 py-2 text-[10px] leading-relaxed text-muted">
        {lang === "bn"
          ? `সর্বোচ্চ ৫টি দেখানো হয়েছে। শর্ত মেলা কোনো পরামর্শ, সম্ভাবনার হিসাব বা অর্ডার নয়।${containsReplay ? " ইতিহাস থেকে পুনর্গঠিত সারি লাইভ আবিষ্কার নয়।" : ""}`
          : `Showing at most five. An observation is not a recommendation, probability estimate, or order.${containsReplay ? " Historical reconstructions are not live discoveries." : ""}`}
      </footer>
    </section>
  );
}
