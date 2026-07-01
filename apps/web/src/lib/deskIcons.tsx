import type { ReactNode } from "react";

// Custom single-colour line glyphs, one per official desk. Consistent 24x24 viewBox, stroke =
// currentColor (so the avatar's text-accent tints them gold). Keyed by handle.
const PATHS: Record<string, ReactNode> = {
  BullsOfDhakaLevels: (
    // support/resistance rails with price between
    <>
      <line x1="4" y1="7" x2="20" y2="7" />
      <line x1="4" y1="17" x2="20" y2="17" />
      <circle cx="12" cy="12" r="2" fill="currentColor" stroke="none" />
    </>
  ),
  BullsOfDhakaVolume: (
    // volume bars
    <>
      <line x1="6" y1="20" x2="6" y2="14" />
      <line x1="10" y1="20" x2="10" y2="8" />
      <line x1="14" y1="20" x2="14" y2="16" />
      <line x1="18" y1="20" x2="18" y2="5" />
    </>
  ),
  BullsOfDhakaForeign: (
    // globe
    <>
      <circle cx="12" cy="12" r="8.5" />
      <line x1="3.5" y1="12" x2="20.5" y2="12" />
      <path d="M12 3.5 C 8 7, 8 17, 12 20.5 C 16 17, 16 7, 12 3.5" />
    </>
  ),
  BullsOfDhakaInstitution: (
    // bank / columns
    <>
      <path d="M4 9 L12 4 L20 9" />
      <line x1="3.5" y1="20" x2="20.5" y2="20" />
      <line x1="7" y1="9.5" x2="7" y2="19" />
      <line x1="12" y1="9.5" x2="12" y2="19" />
      <line x1="17" y1="9.5" x2="17" y2="19" />
    </>
  ),
  BullsOfDhakaSponsor: (
    // person (insider)
    <>
      <circle cx="12" cy="8" r="3.5" />
      <path d="M5.5 20 C 5.5 15, 18.5 15, 18.5 20" />
    </>
  ),
  BullsOfDhakaDividend: (
    // banknote
    <>
      <rect x="3" y="7" width="18" height="10" rx="2" />
      <circle cx="12" cy="12" r="2.5" />
    </>
  ),
  BullsOfDhakaEarnings: (
    // results report
    <>
      <rect x="5" y="3" width="14" height="18" rx="2" />
      <line x1="8.5" y1="8" x2="15.5" y2="8" />
      <line x1="8.5" y1="12" x2="15.5" y2="12" />
      <line x1="8.5" y1="16" x2="13" y2="16" />
    </>
  ),
  BullsOfDhakaRating: (
    // medal
    <>
      <circle cx="12" cy="9" r="5" />
      <path d="M9 13.5 L7.5 21 L12 18 L16.5 21 L15 13.5" />
    </>
  ),
  BullsOfDhakaMarket: (
    // closing bell
    <>
      <path d="M6 17 C 6 11, 8 6.5, 12 6.5 C 16 6.5, 18 11, 18 17 Z" />
      <line x1="4" y1="17" x2="20" y2="17" />
      <path d="M10.5 20 a1.6 1.6 0 0 0 3 0" />
      <line x1="12" y1="4.2" x2="12" y2="6.5" />
    </>
  ),
  BullsOfDhakaMomentum: (
    // trending up
    <>
      <polyline points="4,16 9,11 13,14 20,6" />
      <polyline points="15,6 20,6 20,11" />
    </>
  ),
  BullsOfDhakaStrength: (
    // dumbbell
    <>
      <line x1="7" y1="12" x2="17" y2="12" />
      <rect x="3" y="8.5" width="3" height="7" rx="1" />
      <rect x="18" y="8.5" width="3" height="7" rx="1" />
    </>
  ),
  BullsOfDhakaQuality: (
    // star
    <>
      <polygon points="12,3.5 14.4,9 20.4,9.5 15.8,13.7 17.3,19.5 12,16.3 6.7,19.5 8.2,13.7 3.6,9.5 9.6,9" />
    </>
  ),
  BullsOfDhakaSmartMoney: (
    // lightbulb (insight)
    <>
      <path d="M9.5 18.5 h5 M10.5 21 h3" />
      <path d="M12 3 a6 6 0 0 1 3.5 10.8 c-0.7 0.6 -1 1.4 -1 2.2 h-5 c0 -0.8 -0.3 -1.6 -1 -2.2 a6 6 0 0 1 3.5 -10.8 Z" />
    </>
  ),
  BullsOfDhakaAccumulation: (
    // magnet (absorbing)
    <>
      <path d="M7 4 v7 a5 5 0 0 0 10 0 v-7" />
      <line x1="6.5" y1="4" x2="10.5" y2="4" />
      <line x1="13.5" y1="4" x2="17.5" y2="4" />
    </>
  ),
  BullsOfDhakaCircuit: (
    // lightning bolt
    <>
      <polygon points="13,2.5 5,13.5 11,13.5 10,21.5 19,9.5 13,9.5" />
    </>
  ),
  BullsOfDhakaBreakout: (
    // arrow breaking through a ceiling
    <>
      <line x1="4" y1="7" x2="20" y2="7" strokeDasharray="2.5 2.5" />
      <polyline points="12,21 12,4.5" />
      <polyline points="7.5,9.5 12,4.5 16.5,9.5" />
    </>
  ),
};

export const hasDeskIcon = (handle: string): boolean => handle in PATHS;

export function DeskIcon({ handle, size = 18 }: { handle: string; size?: number }) {
  const paths = PATHS[handle];
  if (!paths) return null;
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.9}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      {paths}
    </svg>
  );
}
