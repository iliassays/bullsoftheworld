// One recognizable icon per official desk, keyed by handle. Rendered as the desk's avatar in the
// feed and on its profile, so each desk reads as a distinct branded account.
const DESK_ICONS: Record<string, string> = {
  BullsOfDhakaLevels: "🪜", // price levels (support/resistance rungs)
  BullsOfDhakaVolume: "🔊", // unusual volume
  BullsOfDhakaForeign: "🌐", // foreign flow
  BullsOfDhakaInstitution: "🏦", // institutional flow
  BullsOfDhakaSponsor: "👤", // insider / sponsor
  BullsOfDhakaDividend: "💵", // dividend cash
  BullsOfDhakaEarnings: "🧾", // results
  BullsOfDhakaRating: "🏅", // credit rating
  BullsOfDhakaMarket: "🔔", // market close bell
  BullsOfDhakaMomentum: "📈", // 12-month trend
  BullsOfDhakaStrength: "💪", // relative strength
  BullsOfDhakaQuality: "⭐", // quality & value
  BullsOfDhakaSmartMoney: "🧠", // smart money
  BullsOfDhakaAccumulation: "🧲", // quiet accumulation (absorbing supply)
  BullsOfDhakaCircuit: "⚡", // circuit limit hit
  BullsOfDhakaBreakout: "🚀", // 52-week breakout
};

export const deskIcon = (handle: string): string | undefined => DESK_ICONS[handle];
