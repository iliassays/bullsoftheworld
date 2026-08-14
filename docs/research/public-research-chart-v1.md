# Public Research Chart v1

## User story

As a Bulls of Dhaka or Bulls of Wall Street user, I can open a ticker and see its completed-session price history, volume, registered trend overlays, and auditable market-condition checks in one place. The chart explains what the data shows without turning a research condition into a prediction or trade instruction.

## Product boundary

The public chart is a ticker-research surface, not a public copy of Atlas.

- Public: adjusted completed-session OHLCV, EMA20, EMA50, support/resistance, active chart-pattern context, and three deterministic research conditions.
- Private Atlas: strategy admission, portfolio construction, risk sizing, paper targets, execution state, and investment-workflow evidence.
- Tenant isolation: the API resolves the symbol inside the request tenant's market and rejects symbols that are inactive or not approved for public research.
- Language: DSE supports Bangla and English; the U.S. portal uses English.

## Architecture

```text
Tenant-bound public request
        |
        v
Active public symbol in tenant market
        |
        v
Completed daily bars -> corporate-action adjustment
        |
        +-> registered overlays (EMA20 / EMA50)
        |
        +-> shared research-conditions-v1 engine
        |       trend alignment
        |       participation expansion
        |       controlled pullback context
        |
        v
PublicResearchChart DTO -> localized ticker chart UI
```

The API projects the shared condition engine into a read-only public contract. It does not duplicate calculation rules in the browser and does not expose Atlas strategy or portfolio state.

## Volume versus volume profile

The histogram below the candles is completed-session volume. It answers how much traded during each session.

A volume profile answers where volume traded across price levels. Daily OHLCV does not contain that distribution. Assigning an entire day's volume to the close, typical price, or a uniform high-low range would create false precision, so v1 reports the capability as unavailable.

Volume profile may be enabled only when the tenant has:

1. Verified trades-at-price or sufficiently complete intraday bars for the displayed period.
2. Documented session and extended-hours treatment.
3. Corporate-action normalization consistent with the chart.
4. Coverage and gap thresholds enforced by data-quality checks.
5. A named method and source frequency returned by the API.

The first valid release should expose point of control, value area, high-volume nodes, low-volume nodes, source frequency, and coverage quality. It must degrade to an explicit unavailable state when those requirements are not met.

## Interpretation guardrails

- A condition marked observed means its deterministic checks passed at the stated completed-session cutoff.
- It is not a probability estimate, target, recommendation, or order.
- Current delayed prices may be newer than the condition cutoff and are labeled separately.
- Transition markers are capped to the most recent observations to preserve chart readability.
- Public explanations show actual values and thresholds so a user can audit why a state was assigned.

## Verification

- API contract tests cover both DSE and U.S. market identities with the same deterministic fixture.
- UI unit tests cover localization, summaries, values, and transition limits.
- Both tenant production builds must pass independently.
- Desktop and 390px mobile visual QA must show no overlap or horizontal page overflow.
