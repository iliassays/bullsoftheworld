import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type Screen } from "../lib/api";
import { Spinner } from "../components/ui";
import { InfoTip } from "../components/InfoTip";
import { useLang } from "../lib/i18n";
import { SCREEN_LESSON } from "../lib/lessons";
import { ScreenRow, metricHeader, screenDesc, screenHelp, screenTitle } from "./Markets";

const GROUP_KEY: Record<string, string> = {
  movers: "group.movers",
  community: "group.community",
  value: "group.value",
  technical: "group.technical",
};
const PERIODS = [
  { id: "1d", label: "1D" },
  { id: "5d", label: "5D" },
  { id: "7d", label: "7D" },
  { id: "15d", label: "15D" },
  { id: "1m", label: "1M" },
];
const WINDOWS = [
  { id: "3m", label: "3M" },
  { id: "6m", label: "6M" },
  { id: "12m", label: "12M" },
];
// Unusual volume: spike (1D) vs sustained interest (5D / 1M).
const VOL_PERIODS = [
  { id: "1d", label: "1D" },
  { id: "5d", label: "5D" },
  { id: "1m", label: "1M" },
];
// Ownership screens: accumulation vs distribution.
const DIRECTIONS = [
  { id: "buy", label: "Buying" },
  { id: "sell", label: "Selling" },
];

// Explore page scoped to ONE category: tabs are that category's screens; the active screen shows
// its full list, with its own timeframe filter attached to the card. "How to read this" lives
// behind the (i) icon, so the data stays front-and-centre.
export function ScreenExplore() {
  const { t, lang } = useLang();
  const { key = "" } = useParams();
  const [all, setAll] = useState<Screen[]>([]);
  const [active, setActive] = useState(key);
  const [period, setPeriod] = useState("1d");
  const [window, setWindow] = useState("12m");
  const [direction, setDirection] = useState("buy");
  const [screen, setScreen] = useState<Screen | null>(null);
  const activeTabRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    api
      .screens()
      .then((r) => setAll(r.screens))
      .catch(() => setAll([]));
  }, []);
  useEffect(() => setActive(key), [key]);

  const group = all.find((s) => s.key === active)?.group;
  const tabs = all.filter((s) => s.group === group && s.items.length > 0);
  const isMover = active === "top_gainers" || active === "top_losers";
  const isMomentum = active === "momentum_12_1";
  const isVolume = active === "unusual_volume";
  const isOwnership = active === "foreign_buying" || active === "institutional_buying";
  const usesPeriod = isMover || isVolume;
  const lessonId = SCREEN_LESSON[active];

  // Keep the selected tab visible — with many categories it otherwise scrolls off-screen.
  useEffect(() => {
    activeTabRef.current?.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
  }, [active, tabs.length]);

  useEffect(() => {
    if (!active) return;
    setScreen(null);
    api
      .screen(
        active,
        50,
        usesPeriod ? period : undefined,
        isMomentum ? window : undefined,
        isOwnership ? direction : undefined,
      )
      .then(setScreen)
      .catch(() => setScreen(null));
  }, [active, period, window, direction, usesPeriod, isMomentum, isOwnership]);

  const tf = isMomentum
    ? { set: WINDOWS, sel: window, choose: setWindow }
    : isOwnership
      ? { set: DIRECTIONS, sel: direction, choose: setDirection }
      : usesPeriod
        ? { set: isVolume ? VOL_PERIODS : PERIODS, sel: period, choose: setPeriod }
        : null;

  return (
    <div className="flex flex-col gap-3">
      <Link to="/markets" className="text-xs text-accent px-1">
        {t("backToMarkets")}
      </Link>
      {group && (
        <div className="text-[11px] uppercase tracking-wide text-muted px-1">
          {GROUP_KEY[group] ? t(GROUP_KEY[group]) : group}
        </div>
      )}

      <div className="flex gap-2 overflow-x-auto pb-1">
        {tabs.map((tb) => (
          <button
            key={tb.key}
            ref={active === tb.key ? activeTabRef : null}
            onClick={() => setActive(tb.key)}
            className={`whitespace-nowrap text-xs font-semibold px-3 py-1.5 rounded-full border ${
              active === tb.key
                ? "text-accent border-accent bg-accent/10"
                : "text-muted border-border"
            }`}
          >
            {screenTitle(tb, lang)}
          </button>
        ))}
      </div>

      {screen === null ? (
        <Spinner />
      ) : (
        <div className="bg-surface border border-border rounded-2xl p-4">
          <div className="flex items-center gap-1.5">
            <div className="font-semibold text-sm text-accent">{screenTitle(screen, lang)}</div>
            <InfoTip
              text={screenHelp(screen.key, lang) ?? screenDesc(screen, lang)}
              lessonId={lessonId}
            />
          </div>
          <div className="text-[11px] text-muted">{screenDesc(screen, lang)}</div>

          {tf && (
            <div className="flex gap-2 mt-2">
              {tf.set.map((p) => (
                <button
                  key={p.id}
                  onClick={() => tf.choose(p.id)}
                  className={`text-[11px] font-semibold px-2.5 py-1 rounded-full ${
                    tf.sel === p.id ? "text-accent bg-accent/10" : "text-muted border border-border"
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
          )}
          {isMover && period === "1m" && (
            <p className="text-[10px] text-muted mt-1">{t("explore.moverReversal")}</p>
          )}
          {isMomentum && (
            <p className="text-[10px] text-muted mt-1">{t("explore.dotsNote")}</p>
          )}

          <div className="mt-3 flex justify-between text-[10px] uppercase tracking-wide text-muted/70 pb-1">
            <span className="pl-7">{t("col.symbol")}</span>
            <span className="flex gap-3">
              <span>{t("col.price")}</span>
              <span className="w-20 text-right">{metricHeader(screen.value_label, t)}</span>
            </span>
          </div>
          <div className="flex flex-col">
            {screen.items.map((it, i) => (
              <ScreenRow key={it.code} item={it} screen={screen} rank={i + 1} />
            ))}
            {screen.items.length === 0 && (
              <div className="text-muted text-sm py-2">{t("nothingHere")}</div>
            )}
          </div>
          <p className="text-[10px] text-muted mt-2">{t("screen.descNote")}</p>
        </div>
      )}
    </div>
  );
}
