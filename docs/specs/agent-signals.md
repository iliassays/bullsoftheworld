# Spec: Agent Signals (auto desk-notes in the feed)

**Status:** Building (Phase 1) · **Owner:** Ilias · **Date:** 2026-06-25

Automated, descriptive **data notes** posted into stock feeds by named system agents
(`bullsofdhaka-<beat>-agent`). Each agent is woken by its data source landing and posts **only on a
material, confirmed change** — never per-ticker spam. Facts + a plain "what it means," never advice.

## Compliance (non-negotiable)
Descriptive + educational only; no buy/sell/target/prediction. Templated + bilingual (no LLM).
Badged 🤖 auto · data note, delayed/as-of stamped. Public side only — never carries `shortlist.py`.

## Agents, by data-authority tier
| Agent (handle) | Fires on | Cadence / publish |
|---|---|---|
| `bullsofdhaka-levels-agent` | new 52w high/low, confirmed breakout/breakdown, 200-DMA cross, RSI into OB/OS | **EOD** (evening + morning brief) |
| `bullsofdhaka-volume-agent` | unusual volume (relvol ≥ 2.5×, day-fraction scaled) | **intraday** (reactive) |
| `bullsofdhaka-foreign-agent` | foreign stake Δ ≥ 1.0pp (new monthly disclosure) | **monthly** (pre-open, 1st trading day) |
| `bullsofdhaka-institution-agent` | institutional Δ ≥ 2.0pp | monthly |
| `bullsofdhaka-sponsor-agent` | sponsor/director Δ ≥ 1.0pp | monthly |
| `bullsofdhaka-dividend-agent` | dividend declared | **news-triggered**, seasonal |
| `bullsofdhaka-earnings-agent` | results / new EPS | news-triggered, seasonal |
| `bullsofdhaka-rating-agent` | credit-rating change | news-triggered, rare |
| `bullsofdhaka-market-update-agent` | daily market wrap | EOD (evening) |

## Thresholds (data-calibrated; v1 starters)
relvol ≥ 2.5× (p97) + avg_volume_20 ≥ 50k floor · foreign Δ ≥ 1.0pp (rare → low) · institution
Δ ≥ 2.0pp (noisy → high) · breakout needs relvol ≥ 1.2 · per-ticker cap ~2 notes/day.

## Mechanics
- **Detect** by comparing `compute(bars)` vs `compute(bars[:-1])` (today vs yesterday) — no coupling
  to the analytics upsert; re-derivable, pull-agnostic.
- **Dedupe ledger** `signal_events` (market, code, event_type, occurrence_key unique) — one note per
  occurrence, ever. Re-runs never duplicate.
- **Publish** = a `Post` (kind=`note`, authored by the agent account) + a `Cashtag` (so it lands on
  the ticker feed) + a `signal_events` row linking the post. Users can react/reply (feeds buzz).
- **Quality gate:** only on valid data, stamped to as-of/disclosure date (omit over mislead).

## Publishing rhythm (the disclosure calendar)
- **Morning brief (pre-open ~9:15):** overnight news + monthly ownership (1st) + yesterday's levels — actionable before the bell.
- **Evening recap (post-close ~18:00):** market wrap + today's levels.
- **Intraday:** volume (reactive). The appointment surface is a scheduled roundup that always posts (even "quiet"); per-ticker notes stay strictly material.

## News source (Phase 2 — new)
DSE has no news/PSI scrape yet. Add `get_news()` + an `announcements` model; news = the timely
trigger for dividend/earnings/rating (news → on-demand `get_company()` pull for exact figures →
publish). Parse pre-open + EOD.

## Phases
- **P1 (now):** foundation (`signal_events`, `Post.kind`, agent accounts, publish+dedupe) +
  **levels-agent** (52w high/low, breakout/breakdown) wired to the EOD path. Feed badging.
- **P2:** volume-agent (intraday) + ownership agents (monthly) + market-update.
- **P3:** news source → dividend/earnings/rating; morning/evening brief scheduler + roundups.
