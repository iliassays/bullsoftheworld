import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useSeo } from "../components/Seo";
import { CompanyLogo } from "../components/CompanyLogo";
import { Spinner } from "../components/ui";
import { api, type BrowseSize } from "../lib/api";
import { useLang } from "../lib/i18n";
import { formatCurrencyMillions } from "../lib/market";
import { Link, useNavigate } from "../lib/nav";
import { useTenantConfig } from "../lib/tenant";
import { useUniverse } from "../lib/universe";
import { ALL_UNIVERSE, normalizeUniverseTier } from "../lib/universe-policy";

// Browse-by-size: the canonical cap tiers as a segmented, URL-addressed page (/size/large).
// Descriptive browse only — ranked by market cap, never by any score. The "Unclassified" bucket
// is reachable on purpose: names without a reliable cap are shown there, never guessed into a
// tier. Whole-market surfaces (Mood, Wrap) are untouched by this page's tier context.
export function SizeBrowse() {
  const { tier = "large" } = useParams();
  const { t, lang } = useLang();
  const { config } = useTenantConfig();
  const { setTier: setUniverseTier } = useUniverse();
  const navigate = useNavigate();
  const [data, setData] = useState<BrowseSize | null | undefined>(undefined);
  const bn = lang === "bn";

  useEffect(() => {
    const selected = normalizeUniverseTier(tier, config.cap_tiers);
    if (selected !== ALL_UNIVERSE) setUniverseTier(selected);
  }, [config.cap_tiers, setUniverseTier, tier]);

  useEffect(() => {
    setData(undefined);
    api
      .browseSize(tier)
      .then(setData)
      .catch(() => setData(null));
  }, [tier]);

  useSeo({
    title: {
      bn: `${t(`tier.${tier}`)} শেয়ার — ${config.exchange_code} | ${config.brand_name}`,
      en: `${t(`tier.${tier}`)} stocks — ${config.exchange_code} | ${config.brand_name}`,
    },
    description: {
      bn: `${config.exchange_code}-এর ${t(`tier.${tier}`)} কোম্পানি, বাজার মূলধন অনুযায়ী সাজানো। আকার বর্ণনা, সুপারিশ নয়।`,
      en: `${config.exchange_code} ${t(`tier.${tier}`)} companies ranked by market cap. Size is descriptive, not a recommendation.`,
    },
  });

  if (data === undefined) return <Spinner />;
  if (data === null)
    return <div className="text-muted text-sm py-6 text-center">{t("nothingHere")}</div>;

  const tabs = [...data.tiers, "unclassified"];
  const countOf = (name: string) => data.counts.find((c) => c.tier === name)?.count ?? 0;

  return (
    <div className="flex flex-col gap-3">
      <div className="px-1">
        <h1 className="text-base font-bold">{t("tier.browseTitle")}</h1>
        {data.as_of && (
          <div className="text-[10px] text-muted">
            {bn ? "তথ্য" : "as of"} {data.as_of} · {bn ? "বিলম্বিত" : "delayed"}
          </div>
        )}
      </div>

      <div className="flex gap-2 overflow-x-auto pb-1">
        {tabs.map((name) =>
          name === "unclassified" && countOf(name) === 0 ? null : (
            <button
              key={name}
              onClick={() => navigate(`/size/${name}`, { replace: true })}
              className={`whitespace-nowrap text-xs font-semibold px-3 py-1.5 rounded-full border ${
                tier === name ? "text-accent border-accent bg-accent/10" : "text-muted border-border"
              }`}
            >
              {t(`tier.${name}`)} · {countOf(name)}
            </button>
          ),
        )}
      </div>

      <div className="bg-surface border border-border rounded-2xl px-4 py-2 divide-y divide-border">
        {data.items.map((it) => (
          <Link key={it.code} to={`/s/${it.code}`} className="flex items-center gap-2.5 py-2.5">
            <CompanyLogo code={it.code} size={30} />
            <div className="min-w-0 flex-1">
              <div className="text-sm font-bold">${it.code}</div>
              <div className="truncate text-[11px] text-muted">
                {(bn && it.name_bn) || it.name_en}
                {it.sector ? ` · ${it.sector}` : ""}
              </div>
            </div>
            <div className="text-right shrink-0">
              <div className="text-sm font-semibold tnum">
                {it.market_cap_mn != null ? formatCurrencyMillions(it.market_cap_mn) : "—"}
              </div>
              <div
                className={`text-[11px] tnum ${
                  it.change_pct == null
                    ? "text-muted"
                    : it.change_pct >= 0
                      ? "text-up"
                      : "text-down"
                }`}
              >
                {it.change_pct == null
                  ? "—"
                  : `${it.change_pct > 0 ? "+" : ""}${it.change_pct.toFixed(2)}%`}
              </div>
            </div>
          </Link>
        ))}
        {data.items.length === 0 && (
          <div className="text-muted text-sm py-3">{t("nothingHere")}</div>
        )}
      </div>
      <p className="text-[10px] text-muted px-1">
        {bn
          ? "আকার কোম্পানির বর্ণনা মাত্র — কোনো সুপারিশ নয়। নির্ভরযোগ্য মূলধন-তথ্য ছাড়া নামগুলো 'অশ্রেণীবদ্ধ'-তে থাকে।"
          : "Size describes the company — it is not a recommendation. Names without reliable cap data stay under 'Unclassified'."}
      </p>
    </div>
  );
}
