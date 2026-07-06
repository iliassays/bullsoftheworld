import { useEffect, useMemo, useState } from "react";
import { useSeo } from "../components/Seo";
import { useNavigate } from "../lib/nav";
import { api, type NoteBeat, type Sector, type SymbolOut } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useLang } from "../lib/i18n";
import { CompanyLogo } from "../components/CompanyLogo";
import { DeskIcon } from "../lib/deskIcons";
import { Spinner } from "../components/ui";

// Post-register onboarding: sectors → stocks → desks, three taps to a seeded feed, watchlist and
// alerts inbox. Skippable at every step — a wall here costs more signups than it seeds.
const STOCKS_SHOWN = 9;

// A few sectors read better with an icon; anything unlisted gets the generic chart.
const SECTOR_ICONS: Record<string, string> = {
  Bank: "🏦",
  "Financial Institutions": "💰",
  Insurance: "🛡️",
  "Fuel & Power": "⚡",
  Pharmaceuticals: "💊",
  "Pharmaceuticals & Chemicals": "💊",
  Textile: "🧵",
  Engineering: "⚙️",
  "Food & Allied": "🍜",
  Cement: "🏗️",
  Telecommunication: "📱",
  IT: "💻",
  "IT Sector": "💻",
};

export function Welcome() {
  const { user } = useAuth();
  const { t, lang } = useLang();
  useSeo({ noindex: true }); // private/personal — keep out of the index
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [sectors, setSectors] = useState<Sector[] | null>(null);
  const [symbols, setSymbols] = useState<SymbolOut[]>([]);
  const [desks, setDesks] = useState<NoteBeat[]>([]);
  const [pickedSectors, setPickedSectors] = useState<Set<string>>(new Set());
  const [pickedStocks, setPickedStocks] = useState<Set<string>>(new Set());
  const [pickedDesks, setPickedDesks] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.sectors().then(setSectors).catch(() => setSectors([]));
    api.symbols(500).then(setSymbols).catch(() => {});
    api.noteBeats().then(setDesks).catch(() => {});
  }, []);

  // Logged-out visitors have nothing to seed — send them to sign in first.
  useEffect(() => {
    if (!user) navigate("/me", { replace: true });
  }, [user, navigate]);

  const candidates = useMemo(() => {
    const inSector = symbols.filter(
      (s) => s.is_active && s.sector != null && pickedSectors.has(s.sector),
    );
    return inSector.slice(0, STOCKS_SHOWN);
  }, [symbols, pickedSectors]);

  const toggle = (set: Set<string>, v: string, apply: (s: Set<string>) => void) => {
    const next = new Set(set);
    if (next.has(v)) next.delete(v);
    else next.add(v);
    apply(next);
  };

  const finish = async () => {
    setSaving(true);
    // Best-effort seeding: a failed add shouldn't strand the user on the welcome screen.
    await Promise.allSettled([
      ...[...pickedStocks].map((code) => api.watchAdd(code)),
      ...[...pickedDesks].map((h) => api.followDesk(h)),
    ]);
    navigate("/", { replace: true });
  };

  const dots = (
    <div className="flex gap-1.5 justify-center py-3">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className={`h-1 rounded-full transition-all ${i === step ? "w-5 bg-accent" : "w-3 bg-border"}`}
        />
      ))}
    </div>
  );

  const skip = (
    <button
      onClick={() => (step < 2 ? setStep(step + 1) : navigate("/", { replace: true }))}
      className="block mx-auto text-xs text-muted mt-3 hover:text-text"
    >
      {t("ob.skip")}
    </button>
  );

  return (
    <div className="flex flex-col gap-3 pt-4">
      <div className="text-center px-2">
        <div className="text-[10px] font-semibold tracking-[0.12em] text-muted uppercase">
          {t("ob.step")} {step + 1} / 3
        </div>
        <h1 className="font-bold text-lg mt-1.5" lang={lang}>
          {step === 0 ? t("ob.sectorsTitle") : step === 1 ? t("ob.stocksTitle") : t("ob.desksTitle")}
        </h1>
        <p className="text-xs text-muted mt-1">
          {step === 0 ? t("ob.sectorsBody") : step === 1 ? t("ob.stocksBody") : t("ob.desksBody")}
        </p>
      </div>

      {step === 0 &&
        (sectors === null ? (
          <Spinner />
        ) : (
          <div className="flex flex-wrap gap-2 justify-center px-2">
            {sectors.map((s) => (
              <button
                key={s.sector}
                onClick={() => toggle(pickedSectors, s.sector, setPickedSectors)}
                className={`text-sm font-semibold px-3.5 py-2 rounded-full border ${
                  pickedSectors.has(s.sector)
                    ? "text-accent border-accent bg-accent/10"
                    : "text-muted border-border"
                }`}
              >
                {SECTOR_ICONS[s.sector] ?? "📈"} {s.sector}
              </button>
            ))}
          </div>
        ))}

      {step === 1 && (
        <div className="bg-surface border border-border rounded-2xl p-3">
          {candidates.length === 0 && (
            <div className="text-sm text-muted text-center py-4">{t("ob.noStocks")}</div>
          )}
          {candidates.map((s) => (
            <button
              key={s.code}
              onClick={() => toggle(pickedStocks, s.code, setPickedStocks)}
              className="flex items-center gap-2.5 py-2.5 w-full text-left border-t border-border first:border-t-0"
            >
              <CompanyLogo code={s.code} size={30} />
              <div className="min-w-0">
                <div className="text-sm font-bold">${s.code}</div>
                <div className="text-[11px] text-muted truncate">
                  {lang === "bn" && s.name_bn ? s.name_bn : s.name_en} · {s.sector}
                </div>
              </div>
              <span
                className={`ml-auto text-xs font-semibold px-2.5 py-1 rounded-full border shrink-0 ${
                  pickedStocks.has(s.code)
                    ? "text-accent border-accent bg-accent/10"
                    : "text-muted border-border"
                }`}
              >
                {pickedStocks.has(s.code) ? `✓ ${t("ob.watching")}` : `＋ ${t("ob.watch")}`}
              </span>
            </button>
          ))}
        </div>
      )}

      {step === 2 && (
        <div className="bg-surface border border-border rounded-2xl p-3">
          {desks.map((d) => (
            <button
              key={d.handle}
              onClick={() => toggle(pickedDesks, d.handle, setPickedDesks)}
              className="flex items-center gap-2.5 py-2.5 w-full text-left border-t border-border first:border-t-0"
            >
              <DeskIcon handle={d.handle} size={30} />
              <div className="min-w-0">
                <div className="text-sm font-bold truncate">
                  {d.name} <span className="text-accent text-xs">✔</span>
                </div>
                <div className="text-[11px] text-muted">@{d.handle}</div>
              </div>
              <span
                className={`ml-auto text-xs font-semibold px-2.5 py-1 rounded-full border shrink-0 ${
                  pickedDesks.has(d.handle)
                    ? "text-accent border-accent bg-accent/10"
                    : "text-muted border-border"
                }`}
              >
                {pickedDesks.has(d.handle) ? `✓ ${t("ob.following")}` : `＋ ${t("ob.follow")}`}
              </span>
            </button>
          ))}
        </div>
      )}

      <button
        onClick={() => (step < 2 ? setStep(step + 1) : finish())}
        disabled={saving || (step === 0 && pickedSectors.size === 0)}
        className="rounded-2xl py-3 text-sm font-bold bg-accent text-bg hover:opacity-90 disabled:opacity-40 mx-2"
      >
        {saving ? "…" : step < 2 ? `${t("ob.continue")} →` : `${t("ob.finish")} 🎉`}
      </button>
      {skip}
      {dots}
    </div>
  );
}
