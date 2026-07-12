# Research beta operating gate

Status: engineering-ready, legal/data-rights clearance pending
Markets: DSE and US
Commercial activity: disabled

## Decision

Operate the product as a free research beta to test whether source-linked evidence saves investors
time and improves research discipline. “Beta” is a product stage, not a legal exemption. Public
availability, personal-data processing and market-data display can still create obligations even
when no money is charged.

## Allowed during the beta

- Free access to descriptive, timestamped and source-linked research tools.
- Watchlists, user-entered portfolios and alerts with explicit delay and no-advice boundaries.
- Consent-gated product analytics and GA4 for activation and retention measurement.
- Anonymous structured feedback; account-linked follow-up only after explicit consent.
- Research interviews with retail users and institutional professionals.
- Educational organic posts that deep-link to the exact evidence shown in the product.

## Disabled until clearance

- Ads, sponsorships, subscriptions, paid reports or paid recommendations.
- Target prices, personalized recommendations, broker connectivity or order routing.
- Institutional pilots, APIs, exports, data feeds, white-labelling or SLAs.
- Claims of regulatory approval, official exchange affiliation, completeness or guaranteed accuracy.
- Paid campaigns that characterize outputs as signals, calls, picks, winners or profit opportunities.

## Required before any public beta deployment

- [x] Persistent research-beta notice and direct correction/feedback path.
- [x] Third-party analytics and ad tracking disabled; first-party behavioral analytics require explicit consent.
- [x] Analytics choice can be changed later from the Me page.
- [x] Raw product analytics retained for at most 180 days; feedback for at most 365 days.
- [x] Institutional page limited to research interviews, with no commercial pilot offer.
- [ ] Operator legal name and German service address added to an operator/legal-notice page.
- [ ] Privacy notice reviewed with the actual operator, processors, hosting locations and legal bases.
- [ ] Written DSE response permitting the intended non-commercial public evaluation, or a licensed
  market-data source whose contract permits the exact display and retention used by the portal.
- [ ] Bangladesh securities counsel confirms which current outputs may be publicly displayed before
  BSEC registration and which must remain descriptive or be removed.
- [ ] German counsel confirms the operator posture, business-registration trigger and financial-law
  perimeter for the beta.

Do not represent unchecked items as solved. Running from Germany and charging nothing reduce some
commercial exposure; they do not establish data-display rights or remove privacy/securities rules.

## Validation cohort

Start with 30 invited DSE users: 10 active traders, 10 long-term investors and 10 newer investors.
Observe at least 15 sessions. Each participant researches one real ticker without a guided demo.

Measure:

| Measure | Initial decision threshold |
|---|---:|
| Registration from qualified visits | >= 5% |
| Three-stock watchlist activation | >= 35% |
| Week-two activated retention | >= 25% |
| Participants completing a ticker task without help | >= 70% |
| Participants saying the product saved meaningful time | >= 60% |
| Incorrect-data reports unresolved after 2 business days | 0 |

These are product hypotheses, not public performance claims. Do not scale acquisition until data
freshness is reliable and the retention threshold is met.

## Decision after four weeks

- **Stop or narrow:** users do not complete research tasks, correction volume is high, or freshness
  is unreliable.
- **Iterate:** activation is promising but week-two retention is below 25%; fix the repeated workflow
  before adding more features.
- **Proceed to formal launch:** users repeatedly return and legal/data-rights opinions define a viable
  operating model. Only then register the appropriate entity and negotiate commercial permissions.

## Evidence to retain

Keep dated copies of methodology, source attribution, model/rule versions, corrections and material
product changes. Do not retain raw user analytics beyond the configured period. If an output evolves
into a formal research report or recommendation, obtain counsel before publication and adopt the
applicable conflict, analyst-credential and record-retention controls.
