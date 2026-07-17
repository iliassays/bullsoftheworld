import { useLang } from "../lib/i18n";
import { useTenantConfig } from "../lib/tenant";
import { useUniverse } from "../lib/universe";
import { ALL_UNIVERSE, type UniverseTier } from "../lib/universe-policy";

// The size filter lives ON the section it scopes (the board lists), not in the global header —
// a control's placement is its jurisdiction. Whole-market widgets sit outside this row and are
// never affected by it, so the boundary is visible instead of implied.
export function SizeChips({ scopeNote }: { scopeNote?: string }) {
  const { t } = useLang();
  const { config } = useTenantConfig();
  const { tier, setTier } = useUniverse();
  const options: UniverseTier[] = [ALL_UNIVERSE, ...(config.cap_tiers as UniverseTier[])];
  return (
    <div className="flex flex-col gap-1">
      <div
        className="flex gap-1.5 overflow-x-auto"
        role="group"
        aria-label={t("tier.universe")}
      >
        {options.map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => setTier(item)}
            className={`whitespace-nowrap text-xs font-semibold px-3 py-1.5 rounded-full border ${
              tier === item ? "text-accent border-accent bg-accent/10" : "text-muted border-border"
            }`}
          >
            {item === ALL_UNIVERSE ? t("tier.all") : t(`tier.${item}`)}
          </button>
        ))}
      </div>
      {scopeNote ? <div className="px-1 text-[10px] text-muted">{scopeNote}</div> : null}
    </div>
  );
}
