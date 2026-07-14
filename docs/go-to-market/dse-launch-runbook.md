# Bulls of Dhaka go-to-market runbook

Owner: product/operator
Market: DSE
Primary language: Bangla
Positioning: **Official evidence and market context, explained clearly before an investor acts.**

Current operating stage: **free research beta**. Follow
[`research-beta-gate.md`](./research-beta-gate.md) before public deployment. The commercial and
institutional sections below describe a future stage; they are not authorized by the beta label.

## 1. What we sell

Do not sell a feature list, AI, RAG, scores or technical indicators. Sell three research outcomes:

1. Understand whether a move has a recent official explanation or only market behaviour.
2. Check liquidity, valuation, ownership, disclosure and crowding risk before acting.
3. Track selected stocks and return when material evidence changes.

Never promise profit, early access to a move, target prices, certainty, or personalized buy/sell
advice. Use “research”, “evidence”, “descriptive”, “as of”, and “decision remains yours”.

## 2. Initial customer segments

| Segment | Daily job | Lead surface | Activation |
|---|---|---|---|
| Active retail | Explain a move and assess entry risk quickly | close wrap, unusual volume, disclosure investigation | watch 10 stocks |
| Long-term retail | Monitor holdings, earnings, dividends and ownership | earnings week, ownership change, portfolio alert | add portfolio + alerts |
| New investor | Understand DSE evidence without jargon | Bangla explainers and worked examples | complete watchlist setup |
| Institution | Reduce repetitive monitoring and improve client research | direct outreach and `/institutions` | qualified 30-day pilot |

## 3. Funnel and metrics

North-star metric: **Weekly Activated Researchers (WAR)**.

A WAR is a signed-in person who views at least three distinct tickers and performs at least one
research action in seven days: watchlist add, alert open, price-alert creation, research question or
idea open. The admin cockpit calculates this from first-party events and ticker views.

| Stage | Event / measure | Initial go/no-go target |
|---|---|---|
| Reach | UTM-attributed visit | establish baseline, no vanity target |
| Interest | `click_launch_signup` | improve copy by source/campaign |
| Registration | `sign_up_completed` | >= 5% of qualified landing visits |
| Activation | `watchlist_activated` with `activation_version=watchlist-10-v1` | >= 35% of new accounts |
| Retention | WAR in following week | >= 25% of activated accounts |
| Institution | persisted lead | 5 discovery calls, then 1 bounded pilot |

Targets are hypotheses for the first 50 real users, not industry guarantees. Do not scale paid
traffic while activation or week-two retention is below target.

## 4. Campaign attribution

Every external link uses:

```text
https://bullsofdhaka.com/bn/s/GP?utm_source=facebook&utm_medium=organic&utm_campaign=close_wrap_2026w29
```

Allowed source values: `facebook`, `youtube`, `tiktok`, `messenger`, `partner`, `email`, `direct`.
Use one campaign name per content series. Never reuse a campaign name for unrelated posts.

## 5. Weekly publishing operation

| Cadence | Content | Destination | CTA |
|---|---|---|---|
| Trading day, pre-open | Three facts to know today | relevant ticker or Markets | inspect the evidence |
| Trading day, after close | Close wrap with three notable names | ticker pages | track this stock |
| Tue / Thu | One official-catalyst investigation | Ask this stock | review sources |
| Event-driven | earnings, dividend, ownership or disclosure | exact ticker tab | add to watchlist |
| Weekend | one Bangla educational case | Trust, Patterns or ticker | research three names |

Each post must contain a date/as-of label, a source class, one clear finding, one limitation, one
deep link and one CTA. Avoid generic “market update” posts and screenshots without a useful link.

## 6. Four-week launch sequence

### Week 1: evidence and interviews

- Recruit 8 active traders, 8 long-term investors and 4 beginners.
- Observe each person researching one stock; do not demo until after the task.
- Ask what decision they were making, where they looked, what they distrusted, and what they missed.
- Record time-to-answer, sources opened, watchlist completion and next-day return.

### Week 2: organic acquisition

- Publish the full trading-day cadence with UTM links.
- Secure permission from three relevant Facebook-group administrators.
- Compare three hooks: official reason, risk before entry, and never miss an event.
- Promote only posts that already generate qualified ticker visits organically.

### Week 3: bounded paid test

- Cap the first test at BDT 10,000 total across three proven creatives.
- Optimize for registration/watchlist activation, not page likes, reach or raw link clicks.
- Stop a source when it produces volume without activated users.
- Financial ad copy must describe a research tool, not returns or signals.

### Week 4: retention and sales

- Interview users who activated and users who abandoned onboarding.
- Remove or de-emphasize homepage elements that do not support a repeated research job.
- Run five institutional discovery calls and qualify one pilot by workflow, data rights and owner.
- Publish a transparent monthly product/data-quality note.

## 7. Institutional pilot gate (future, disabled in research beta)

Before accepting money, document the target workflow, named users, data and redistribution rights,
feature scope, security, SLA, correction process, success measures, pricing, termination and data
deletion. Sell monitoring coverage, evidence provenance, workflow speed and client engagement, not
alpha or returns. Move each cockpit lead through `new`, `contacted`, `qualified`, and `closed`.

## 8. Regulatory and trust gate

- Obtain Bangladesh securities counsel before charging for security-specific recommendations,
  ratings or subscription research.
- Confirm whether the operator requires registration under the BSEC Research Analysis Rules.
- Confirm DSE and third-party data display/redistribution rights before a B2B pilot.
- Keep source, as-of time, delay, correction path and no-advice boundary visible.
- Review the current [BSEC Research Analysis Rules](https://sec.gov.bd/lbook/F-10_2015.pdf),
  [Google financial advertising policy](https://support.google.com/adspolicy/answer/2464998), and
  [Meta financial-products policy](https://www.facebook.com/policies/ads/prohibited_content/prohibited_financial_products_and_services)
  before launching paid campaigns.

## 9. AdSense gate

AdSense is disabled during the research beta. Apply only after sustained organic use, original indexable research,
public trust/privacy/terms pages and a stable page experience. Keep ads outside portfolio, alerts,
forms and decision-critical evidence panels. Never buy or encourage ad clicks.

## 10. Launch checklist

- [ ] Production migration applied and API/web/admin health checks pass.
- [ ] Registration to ten-stock activation works in Bangla and English on mobile.
- [ ] Product events appear in the cockpit without raw PII.
- [ ] Institutional form creates a lead and status can be updated.
- [ ] `/trust`, `/privacy`, `/terms`, and `/institutions` render for humans and crawlers.
- [ ] Sitemap regenerated and Search Console resubmitted.
- [ ] Facebook links use UTMs and land on the exact promised evidence.
- [ ] Legal/data-rights review complete before paid research or institutional data delivery.
- [ ] Support and correction email is monitored daily.
- [ ] Weekly funnel review is scheduled; feature output is not counted as customer impact.
