export const ATLAS_EXPERIENCE_VERSION = "orientation-v1";

export type AtlasTenant = "bullsofdhaka" | "bullsofwallst";
export type AnalyticsConsent = "granted" | "denied" | null;
export type OnboardingOutcome = "completed" | "skipped";
export type WorkflowStage =
  | "command"
  | "discover"
  | "investigate"
  | "validate"
  | "allocate"
  | "learn"
  | "operate";

export interface AtlasExperienceIdentity {
  tenant: AtlasTenant;
  userId: number;
}

export interface OrientationStep {
  body: string;
  guardrail: string;
  key: Exclude<WorkflowStage, "command" | "operate">;
  label: string;
  route: string;
  title: string;
}

export interface GlossaryEntry {
  category: "Evidence" | "Research" | "Strategy" | "Risk" | "Outcomes";
  meaning: string;
  route?: string;
  term: string;
  not: string;
}

interface StorageReader {
  getItem(key: string): string | null;
}

interface StorageWriter extends StorageReader {
  setItem(key: string, value: string): void;
}

export const ORIENTATION_STEPS: readonly OrientationStep[] = [
  {
    key: "discover",
    label: "Discover",
    title: "Start with dated observations",
    body: "Setup Monitor, Condition Scanner, and Catalysts surface point-in-time facts worth inspecting.",
    guardrail: "A setup is research evidence. It is not a recommendation, target, or order.",
    route: "/setups",
  },
  {
    key: "investigate",
    label: "Investigate",
    title: "Build the evidence case",
    body: "Research Inbox prioritizes new evidence; Company Research connects price behavior, filings, fundamentals, and counter-evidence.",
    guardrail: "Research urgency measures attention required, not expected return.",
    route: "/queue",
  },
  {
    key: "validate",
    label: "Validate",
    title: "Demand evidence from the strategy",
    body: "Strategy Lab evaluates registered rules across costs, robustness checks, historical diagnostics, and forward collection.",
    guardrail: "A strategy remains diagnostic until every promotion gate is satisfied.",
    route: "/hypotheses",
  },
  {
    key: "allocate",
    label: "Allocate",
    title: "Let risk decide what can enter the book",
    body: "Portfolio & Risk shows target changes, sizing constraints, exposures, paper executions, and interventions.",
    guardrail: "Only a registered, admitted, and risk-sized strategy can create a paper target.",
    route: "/portfolio",
  },
  {
    key: "learn",
    label: "Learn",
    title: "Judge outcomes, not narratives",
    body: "Research Outcomes preserves forward observations, favorable and adverse paths, and calibration by horizon.",
    guardrail: "Historical reconstruction and forward evidence are labelled separately and must not be mixed.",
    route: "/memory",
  },
] as const;

export const GLOSSARY: readonly GlossaryEntry[] = [
  {
    term: "Evidence cutoff",
    category: "Evidence",
    meaning: "The latest timestamp Atlas was allowed to know when producing the displayed result.",
    not: "A guarantee that every possible source had published by that time.",
  },
  {
    term: "Setup",
    category: "Research",
    meaning: "A deterministic market pattern observed at a recorded point in time.",
    not: "A buy signal, forecast, target, or execution instruction.",
    route: "/setups",
  },
  {
    term: "Confirmed setup",
    category: "Research",
    meaning: "The final rule in a setup taxonomy was satisfied on a completed observation.",
    not: "Proof of high probability, strategy admission, or profitability.",
    route: "/setups",
  },
  {
    term: "Research urgency",
    category: "Research",
    meaning: "How quickly new evidence should be investigated based on freshness and materiality.",
    not: "Expected return or a ranking of what to buy first.",
    route: "/queue",
  },
  {
    term: "Counter-evidence",
    category: "Evidence",
    meaning: "Facts that weaken, contradict, or bound the current investment interpretation.",
    not: "A cosmetic disclaimer; it must remain visible in the decision record.",
  },
  {
    term: "Registered strategy",
    category: "Strategy",
    meaning: "A versioned, reproducible rule set with a declared universe, entry, exit, sizing, and cost model.",
    not: "An analyst opinion or a scanner row selected after seeing its outcome.",
    route: "/hypotheses",
  },
  {
    term: "Promotion gate",
    category: "Strategy",
    meaning: "A pre-declared evidence threshold a strategy must pass before forward paper allocation is permitted.",
    not: "A manual approval that can waive failed evidence after the fact.",
    route: "/hypotheses",
  },
  {
    term: "Target",
    category: "Risk",
    meaning: "The next-session portfolio weight requested by an admitted strategy after risk constraints.",
    not: "A price target or a promise that an execution will occur.",
    route: "/portfolio",
  },
  {
    term: "Paper execution",
    category: "Risk",
    meaning: "A simulated fill using the system's recorded execution assumptions and observable market data.",
    not: "A live broker fill or proof the same liquidity was available for real capital.",
    route: "/portfolio",
  },
  {
    term: "Planning objective",
    category: "Risk",
    meaning: "A risk-to-reward reference derived from the recorded invalidation distance.",
    not: "A forecast or claimed future price.",
  },
  {
    term: "MFE",
    category: "Outcomes",
    meaning: "Maximum favorable excursion: the best observed move after the recorded reference point.",
    not: "A realizable return unless an exit rule captured it.",
    route: "/memory",
  },
  {
    term: "MAE",
    category: "Outcomes",
    meaning: "Maximum adverse excursion: the worst observed move after the recorded reference point.",
    not: "The final loss or a substitute for drawdown and stop modeling.",
    route: "/memory",
  },
  {
    term: "Forward outcome",
    category: "Outcomes",
    meaning: "Performance measured after a decision was timestamped and frozen, using later observations only.",
    not: "A reconstructed backtest or a result selected with hindsight.",
    route: "/memory",
  },
  {
    term: "Calibration",
    category: "Outcomes",
    meaning: "A comparison between stated confidence and what subsequently occurred across a sufficient sample.",
    not: "Accuracy inferred from one winner, one loss, or an immature observation.",
    route: "/memory",
  },
  {
    term: "Reconstructed evidence",
    category: "Evidence",
    meaning: "A historical state rebuilt from stored point-in-time inputs under a declared method version.",
    not: "Forward performance; survivorship and source limitations still apply.",
  },
  {
    term: "Data blocked",
    category: "Evidence",
    meaning: "Atlas lacks a required dataset or entitlement and has stopped that analysis explicitly.",
    not: "A neutral signal or permission to replace the missing input with a proxy.",
  },
] as const;

function identityPrefix(identity: AtlasExperienceIdentity): string {
  return `bulls.atlas.${identity.tenant}.user.${identity.userId}`;
}

export function experienceStorageKeys(identity: AtlasExperienceIdentity) {
  const prefix = identityPrefix(identity);
  return {
    analyticsConsent: `${prefix}.analytics-consent.v1`,
    onboarding: `${prefix}.onboarding.${ATLAS_EXPERIENCE_VERSION}`,
    session: `${prefix}.analytics-session.v1`,
  } as const;
}

function browserLocalStorage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function readAnalyticsConsent(
  identity: AtlasExperienceIdentity,
  storage: StorageReader | null = browserLocalStorage(),
): AnalyticsConsent {
  if (!storage) return null;
  try {
    const value = storage.getItem(experienceStorageKeys(identity).analyticsConsent);
    return value === "granted" || value === "denied" ? value : null;
  } catch {
    return null;
  }
}

export function writeAnalyticsConsent(
  identity: AtlasExperienceIdentity,
  value: Exclude<AnalyticsConsent, null>,
  storage: StorageWriter | null = browserLocalStorage(),
): void {
  if (!storage) return;
  try {
    storage.setItem(experienceStorageKeys(identity).analyticsConsent, value);
  } catch {
    // Atlas remains usable when storage is unavailable; analytics stays fail-closed.
  }
}

export function shouldShowOrientation(
  identity: AtlasExperienceIdentity,
  storage: StorageReader | null = browserLocalStorage(),
): boolean {
  if (!storage) return true;
  try {
    const value = storage.getItem(experienceStorageKeys(identity).onboarding);
    return value !== "completed" && value !== "skipped";
  } catch {
    return true;
  }
}

export function writeOrientationOutcome(
  identity: AtlasExperienceIdentity,
  outcome: OnboardingOutcome,
  storage: StorageWriter | null = browserLocalStorage(),
): void {
  if (!storage) return;
  try {
    storage.setItem(experienceStorageKeys(identity).onboarding, outcome);
  } catch {
    // Failure to persist simply means the orientation may be offered again.
  }
}

export function filterGlossary(query: string): readonly GlossaryEntry[] {
  const normalized = query.trim().toLocaleLowerCase();
  if (!normalized) return GLOSSARY;
  return GLOSSARY.filter((entry) =>
    [entry.term, entry.category, entry.meaning, entry.not]
      .join(" ")
      .toLocaleLowerCase()
      .includes(normalized),
  );
}

const KNOWN_ROUTES = new Set([
  "/today",
  "/queue",
  "/companies",
  "/catalysts",
  "/conditions",
  "/setups",
  "/hypotheses",
  "/operations",
  "/portfolio",
  "/memory",
]);

export function sanitizeAtlasPath(pathname: string): string {
  const path = pathname.split(/[?#]/, 1)[0] || "/";
  if (/^\/companies\/[^/]+\/?$/.test(path)) return "/companies/:ticker";
  const normalized = path.length > 1 ? path.replace(/\/$/, "") : path;
  return KNOWN_ROUTES.has(normalized) ? normalized : "/other";
}

export function workflowStageForPath(pathname: string): WorkflowStage | null {
  switch (sanitizeAtlasPath(pathname)) {
    case "/today":
      return "command";
    case "/setups":
    case "/conditions":
    case "/catalysts":
      return "discover";
    case "/queue":
    case "/companies":
    case "/companies/:ticker":
      return "investigate";
    case "/hypotheses":
      return "validate";
    case "/portfolio":
      return "allocate";
    case "/memory":
      return "learn";
    case "/operations":
      return "operate";
    default:
      return null;
  }
}

export function elapsedBucket(elapsedMs: number): "under_2m" | "2_to_10m" | "over_10m" {
  if (elapsedMs < 2 * 60_000) return "under_2m";
  if (elapsedMs < 10 * 60_000) return "2_to_10m";
  return "over_10m";
}
