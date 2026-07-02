# Feature audit — July 2026

Two-lens review of the shipped product: retail trader (does it delight or overwhelm?) and
institutional/hedge-fund head (where is the real intelligence?). Companion to
`platform-intelligence-research-2026-07.md`.

## Verdict in one paragraph

The codebase is *not* bloated in the engineering sense — no dead code, no half-built UI, every
route live, real quant plumbing underneath. The bloat is **presentational redundancy**: the same
underlying data (`ticker_analytics`) is re-presented through 4 discovery surfaces, 3 prose
narrators, and 3 scoring systems. Each is individually good; stacked together they overwhelm a
retail user and dilute trust ("why do the Scorecard, the Lens, and the Pulse disagree about the
same stock?"). Meanwhile the two features retail actually retains on — alerts and portfolio —
don't exist, and the highest-edge institutional data (ownership deltas, block trades, disclosure
red flags) is ingested-but-under-exploited or not ingested at all.

## The redundancy map (the "bloat")

| Question the user asks | Surfaces answering it today |
|---|---|
| "Which stocks should I look at?" | Markets (20+ screens) · Scanner (10 setups) · ScreenExplore · Today's Watch widget · Trending |
| "Tell me about this stock in words" | PlainReadCard · ExplainCard (LLM) · DigestPanel — 3 prose summaries on ONE Overview tab |
| "Is this stock good quality?" | ScorecardCard (5 dims) · InvestorLensCard (5 personas) · PulseGauges — ~15 scores per stock |

Symbol Overview alone stacks 9 cards. Markets.tsx is 1300+ lines / 70KB. A Dhaka retail user on a
budget Android phone wants: price, chart, one honest read, red flags, what people are saying.

## Retail hat

**What retail will love (keep, promote):**
- Dhaka Mood gauge — simple, emotional, shareable; the CNN fear/greed of DSE
- Delayed-but-honest labels, verify-next checklists, ADTV/safe-order-size guide (genuinely rare)
- Bangla-first everything, logos, earnings week, watchlist
- Bulls desk notes as content (low-noise, factual)

**What retail will bounce off:**
- Choice paralysis across Markets/Scanner/Explore — no single "start here" surface
- Jargon-dense defaults: CMF, OBV slope, "Momentum 12-1", ownership pp deltas (lessons help but the
  default surface is quant-first, explanation-second)
- 8 tabs on a symbol page; 9 cards on Overview
- No reason to come back daily: **no alerts, no portfolio, no streak/learning loop**

**What retail is missing (ranked by retention impact):**
1. **Price/signal alerts + push notifications** — the #1 retention feature in every retail app.
   The backend already produces `SignalEvent`s (52W, breakout, MA200, RSI) — they're published to
   the feed but never *delivered* to the individual who watches that stock. Closest-to-done gap.
2. **Portfolio tracker** — "how am I doing?" is retail's actual daily question. Watchlist ≠
   holdings; no buy price, no P&L. StockNow ships a portfolio ledger; we don't.
3. **Onboarding personalization** — no "pick 3 sectors / 5 stocks" step; new users land on an
   empty feed with a sign-in pitch.
4. **Gamified learning loop** — LearnSheet exists but no quizzes/streaks/badges (the
   descriptive-only moat strategy says gamify *learning*, not trading).

## Institution hat

**Legitimately institutional-lite (the real assets):**
- Precomputed `TickerAnalytics`: 30+ metrics nightly, sector-relative P/E, factor-style dims,
  self-normalized volume z-scores — better plumbing than any local competitor
- Backtest discipline (Scheme-3 flagship, Phase-0 validated trending) — most retail apps never do this
- Compliance gates + moderation audit trail (BSEC-defensible)
- Buzz/attention metrics — the seed of a StockTwits-style Social RSI; proprietary once community grows

**Where the edge is being left on the table:**
1. **Ownership intelligence is the biggest miss.** `ShareholdingSnapshot` (sponsor/institute/
   foreign/public + deltas) is ingested and feeds screens, but the ownership *signals agent is a
   stub* — no "sponsor stake dropped 2pp this month" narrative alerts, no block-trade ingestion at
   all. This is the Fintel-style differentiator (research Tier 1) nobody local synthesizes.
2. **Disclosure red-flag inputs not ingested**: DSE's going-concern threat list and
   financial-statement submission status (both free, verified) would upgrade Red Flags from
   "derived from numbers" to "regulatory early-warning."
3. **Number soup without hierarchy**: Scorecard + Lens + Pulse re-present the same analytics; an
   institution reads that as decoration, not information. One canonical scoring view, the rest as
   drill-down.
4. Hedge/backtest research (38 scripts) not surfaced anywhere — fine as R&D, but decide: product
   input or private tooling.

## Recommendations (discussion basis, not yet actioned)

1. **Consolidate discovery to one front door.** Scanner = "Ideas" (curated, explained, backtested);
   Markets = reference browser for those who ask; fold ScreenExplore into Markets; Today's Watch
   widget links into Scanner. Kill nothing in backend — this is a UI hierarchy change.
2. **Slim Symbol Overview to 5 cards**: Chart · one merged narrative (Plain Read absorbs Digest +
   Explain) · Scorecard + Red Flags · Key Levels · Before-You-Trade. Lens/Pulse move behind the
   Lens tab.
3. **Merge Bulls tab into Feed** (filter chip) → frees a bottom-nav slot for **Portfolio** or
   **Alerts**.
4. **Ship watchlist alerts** on existing SignalEvents (in-app inbox first, push later). Smallest
   work, largest retention payoff.
5. **Build ownership intelligence next** (finish the stub agent + ingest block trades +
   going-concern/submission-status lists) — the institutional edge retail can't get anywhere else.

## Inventory reference

Backend surface (all live-verified by exploration): auth, posts/reactions/threads/sentiment,
moderation cascade L0–L4 with audit log, watchlist, desks/follows, quotes/bars/company/logos/
earnings-calendar, digest, buzz, plain read, levels agent (8 signal types), explainer (LLM,
cached, gated), scorecard + red flags, investor lens, pulse, screener (15+ boards, ~1600 lines),
scanner (~950 lines), trending, news classification (materiality 0–100, decoded details),
mood index, Facebook publishing (cards + idempotent), admin/moderation UI, multi-tenancy,
full EN/BN. Stubs: ownership/volume/factors/market/news signal agents (partial), RAG, scenarios,
hedge research scripts. Absent: notifications, portfolio, trading.

Frontend surface: 13 routes; nav = Feed / Markets / Bulls / Scanner / Me; home = 5 widgets +
composer + feed; Markets = 20+ screens × timeframes; Scanner = 10 setups × explanation sheets;
Symbol = 8 tabs (Overview alone: 9 cards). No dead code or half-built UI found.
