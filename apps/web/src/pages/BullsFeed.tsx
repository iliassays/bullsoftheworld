import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Post, type Quote } from "../lib/api";
import { useLang } from "../lib/i18n";
import { useInfiniteFeed } from "../lib/useInfiniteFeed";
import { Empty, Pct, Spinner, taka } from "../components/ui";

// Per-beat presentation: icon + bilingual name + a one-line "what this means" intro. Keyed by the
// agent beat parsed from the handle (bullsofdhaka-<beat>-agent).
const BEATS: Record<string, { icon: string; en: string; bn: string; introEn: string; introBn: string }> = {
  volume: { icon: "🔊", en: "Unusual volume", bn: "অস্বাভাবিক ভলিউম", introEn: "Trading far above their usual pace today", introBn: "আজ স্বাভাবিকের চেয়ে অনেক বেশি লেনদেন হচ্ছে" },
  accumulation: { icon: "🧲", en: "Quiet accumulation", bn: "নীরব সঞ্চয়", introEn: "Money flowing in while the price stays flat", introBn: "দাম স্থির থাকতেই অর্থ ঢুকছে" },
  momentum: { icon: "📈", en: "Strongest trend", bn: "শক্তিশালী প্রবণতা", introEn: "Strongest 12-month trends", introBn: "সবচেয়ে শক্তিশালী ১২-মাসের প্রবণতা" },
  strength: { icon: "💪", en: "Relative strength", bn: "আপেক্ষিক শক্তি", introEn: "Rising while the market fell", introBn: "বাজার পড়লেও উপরে উঠেছে" },
  quality: { icon: "⭐", en: "Quality & value", bn: "মান ও ভ্যালু", introEn: "Cheap vs sector with strong returns", introBn: "খাতের চেয়ে সস্তা, শক্তিশালী মুনাফা" },
  smartmoney: { icon: "🏦", en: "Smart money", bn: "স্মার্ট মানি", introEn: "Institutions + foreign accumulating", introBn: "প্রতিষ্ঠান ও বিদেশি একসাথে সঞ্চয় করছে" },
  foreign: { icon: "🌐", en: "Foreign flow", bn: "বিদেশি প্রবাহ", introEn: "Foreign ownership changes", introBn: "বিদেশি মালিকানায় পরিবর্তন" },
  institution: { icon: "🏛️", en: "Institutional flow", bn: "প্রাতিষ্ঠানিক প্রবাহ", introEn: "Institutional ownership changes", introBn: "প্রাতিষ্ঠানিক মালিকানায় পরিবর্তন" },
  sponsor: { icon: "👤", en: "Insider / sponsor", bn: "স্পনসর / পরিচালক", introEn: "Sponsor/director stake changes", introBn: "স্পনসর/পরিচালকের অংশে পরিবর্তন" },
  dividend: { icon: "💵", en: "Dividend", bn: "লভ্যাংশ", introEn: "Dividend updates", introBn: "লভ্যাংশ সংক্রান্ত হালনাগাদ" },
  earnings: { icon: "📊", en: "Earnings", bn: "আয়", introEn: "Earnings updates", introBn: "আয় সংক্রান্ত হালনাগাদ" },
  rating: { icon: "🏅", en: "Credit rating", bn: "ক্রেডিট রেটিং", introEn: "Rating updates", introBn: "রেটিং হালনাগাদ" },
  levels: { icon: "🎯", en: "Price levels", bn: "মূল লেভেল", introEn: "Notable support / resistance setups", introBn: "উল্লেখযোগ্য সাপোর্ট / রেজিস্ট্যান্স" },
  market: { icon: "📰", en: "Market update", bn: "মার্কেট আপডেট", introEn: "Market-wide note", introBn: "বাজারজুড়ে নোট" },
};

function beatOf(handle: string): string {
  const m = handle.match(/^bullsofdhaka-(.+)-agent$/);
  const beat = m ? m[1] : "market";
  return beat.startsWith("market") ? "market" : beat;
}

function ago(iso: string): string {
  const s = Math.max(1, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

type Group = { beat: string; day: string; posts: Post[] };

export function BullsFeed() {
  const { t, lang } = useLang();
  const { items, loading, sentinelRef } = useInfiniteFeed("bulls", (l, o) =>
    api.feed(undefined, "note", l, o),
  );
  const [quotes, setQuotes] = useState<Record<string, Quote>>({});

  // Group notes by beat + calendar day so 6 "volume" notes become one scannable card.
  const groups = useMemo<Group[]>(() => {
    const map = new Map<string, Group>();
    for (const p of items) {
      if (p.kind !== "note") continue;
      const beat = beatOf(p.author.handle);
      const day = p.created_at.slice(0, 10);
      const key = `${beat}|${day}`;
      const g = map.get(key) ?? { beat, day, posts: [] };
      g.posts.push(p);
      map.set(key, g);
    }
    return [...map.values()];
  }, [items]);

  // Live price/change for every ticker mentioned (one batched call), so each row feels current.
  const codesKey = useMemo(
    () => [...new Set(items.flatMap((p) => p.cashtags))].sort().join(","),
    [items],
  );
  useEffect(() => {
    const codes = codesKey ? codesKey.split(",") : [];
    if (!codes.length) return;
    api
      .quotes(codes)
      .then((qs) => setQuotes(Object.fromEntries(qs.map((q) => [q.code, q]))))
      .catch(() => {});
  }, [codesKey]);

  return (
    <div className="flex flex-col gap-3">
      <div className="bg-surface border border-border rounded-2xl p-4">
        <div className="text-accent font-semibold text-sm">🐂 {t("bulls.feedTitle")}</div>
        <p className="text-xs text-muted mt-1">{t("bulls.feedDesc")}</p>
      </div>

      {groups.map((g) => {
        const meta = BEATS[g.beat] ?? BEATS.market;
        // Unique tickers in this group (newest note per code wins).
        const byCode = new Map<string, Post>();
        for (const p of g.posts) {
          const code = p.cashtags[0];
          if (code && !byCode.has(code)) byCode.set(code, p);
        }
        const rows = [...byCode.entries()];
        return (
          <div key={`${g.beat}|${g.day}`} className="bg-surface border border-border rounded-2xl p-4">
            <div className="flex items-center gap-2">
              <span className="text-accent font-semibold text-sm">
                {meta.icon} {lang === "bn" ? meta.bn : meta.en}
              </span>
              <span className="text-[11px] text-muted">· {rows.length}</span>
              <span className="ml-auto text-[10px] text-muted">{ago(g.posts[0].created_at)}</span>
            </div>
            <p className="text-[11px] text-muted mt-0.5">{lang === "bn" ? meta.introBn : meta.introEn}</p>

            <div className="mt-2 flex flex-col">
              {rows.map(([code]) => {
                const q = quotes[code];
                return (
                  <Link
                    key={code}
                    to={`/s/${code}`}
                    className="flex items-center justify-between gap-2 py-1.5 border-t border-border/60 first:border-t-0"
                  >
                    <span className="font-bold text-[13px]">${code}</span>
                    {q && (
                      <span className="flex items-baseline gap-2 shrink-0 text-xs tnum">
                        <span className="text-muted">{taka(q.ltp)}</span>
                        <Pct value={q.change_pct} />
                      </span>
                    )}
                  </Link>
                );
              })}
            </div>
            <p className="text-[10px] text-muted mt-2">{t("bulls.feedDescNote")}</p>
          </div>
        );
      })}

      {loading && <Spinner />}
      {!loading && groups.length === 0 && <Empty>{t("bulls.empty")}</Empty>}
      <div ref={sentinelRef} />
    </div>
  );
}
