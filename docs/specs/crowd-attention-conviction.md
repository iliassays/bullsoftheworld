# Spec: Crowd Attention & Conviction layer

**Status:** Draft (for review) · **Owner:** Ilias · **Date:** 2026-06-25
**Surface:** Symbol detail page, "What's happening" digest, screener, Today's Watch

---

## 1. Problem & intent

The Symbol page is where a retail trader decides what to make of a ticker. Today it shows price,
technicals, levels, and a flat post feed. We have a lot of *latent* social signal (watchlist,
post sentiment, reply threading) that we don't surface or aggregate.

The goal is **not** to add StockTwits-style vanity counters. It is to build a small, trustworthy
**attention & conviction** layer that helps a retail trader answer: *how much is the crowd paying
attention to this, how much conviction is behind what they're saying, and is that changing?* —
strictly descriptively, never as a call to act.

This spec unifies three product ideas into one layer:
1. Aggregate "watchers" + their **trend** (reframing the "people love this ticker" idea).
2. Reactions + replies on posts → **conviction / discussion depth** (the highest-value piece).
3. Page-view tracking → **internal analytics only**, optionally a deweighted input (never a
   standalone user-facing "views trending" claim).

## 2. Principles & guardrails (non-negotiable)

These follow the locked product direction (descriptive TA, no advice) and the "omit over mislead"
rule:

- **Descriptive, never advisory or causal.** "Attention is rising," never "about to break out" or
  "buy/sell."
- **Trend over vanity.** Surface *change vs a baseline* ("3× the usual chatter", "watchers +40%
  this week"), not raw absolute counts that just fuel FOMO.
- **Thresholded — omit when thin.** DSE's community is small and easily skewed; show a signal only
  when it clears both a relative threshold (e.g. ≥2× baseline) **and** an absolute floor (e.g. ≥5
  posts). Below that, show nothing rather than something noisy.
- **Anti-gaming.** One reaction per user per post; rate limits; watchers counted from real
  accounts only; no public "dislike" pile-ons.
- **Honest cold-start.** Trends need history. Until the daily snapshot has accumulated N days,
  trend fields return `null` and the UI omits them — we do not back-fill or fake a baseline.

## 3. Concept & signal inventory

A per-ticker "attention & conviction" picture built only from signals we can stand behind:

| Signal | Source | Status | What it tells a trader |
|---|---|---|---|
| Post volume + sentiment | `posts` / `cashtags` | exists | how much chatter, leaning bull/bear |
| Reactions (agree / disagree) | **new** `post_reactions` | build | conviction behind a view |
| Reply / thread depth | `posts.parent_id` | modeled, not surfaced | real discussion vs drive-by |
| Watchers + 7-day trend | `watchlist_items` | exists, not aggregated | attention / following, and its direction |
| Unique viewers | **new** `page_view_events` | optional, internal | raw curiosity (deweighted, never standalone) |

## 4. Data model

New / changed tables (SQLAlchemy, matching existing style in `packages/core/.../models`).

### 4.1 `post_reactions` (new) — Phase A

```python
class PostReaction(Base):
    __tablename__ = "post_reactions"
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    kind: Mapped[str] = mapped_column(String(8))  # 'agree' | 'disagree'
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

- Composite PK `(post_id, user_id)` enforces one reaction per user per post; changing kind is an
  upsert, removing is a delete.
- `kind` deliberately limited to agree/disagree (conviction), not a generic "like" (vanity).
  Open question 6.1: agree/disagree vs an explicit bull/bear vote.

### 4.2 Replies — Phase A (no schema change)

`posts.parent_id` already exists. Needs: a thread read endpoint and `reply_count` /
reaction tallies in `PostOut`.

### 4.3 `ticker_buzz_daily` (new) — Phase B

One row per (market, code, date), written by the EOD scheduler alongside `TickerAnalytics`.
Mirrors that snapshot pattern so trend math is reliable and cheap to read.

```python
class TickerBuzzDaily(Base):
    __tablename__ = "ticker_buzz_daily"
    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    posts_24h: Mapped[int]
    reactions_24h: Mapped[int]
    replies_24h: Mapped[int]
    watchers_total: Mapped[int]        # cumulative snapshot → trend = today vs N days ago
    unique_viewers_24h: Mapped[int | None] = mapped_column(default=None)  # Phase D
    computed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

Storing `watchers_total` as a daily snapshot avoids the "delete loses history" problem (watchlist
removals erase the row), so watcher trend stays correct.

### 4.4 `page_view_events` (new) — Phase D, optional, internal

Append-only, lightweight (`market`, `code`, `user_id?`, `session_hash`, `created_at`). Aggregated
into `unique_viewers_24h`. Never queried directly by a user-facing endpoint as "views rising."

## 5. API

| Method | Path | Phase | Notes |
|---|---|---|---|
| POST | `/posts/{id}/react` | A | body `{kind}`; upsert; 1/user/post |
| DELETE | `/posts/{id}/react` | A | remove caller's reaction |
| GET | `/posts/{id}/replies` | A | thread under a post |
| — | `/posts` (feed) extended | A | add `reply_count`, `agree`, `disagree`, `my_reaction` to `PostOut` |
| GET | `/symbols/{code}/buzz` | B | attention picture (below) |
| — | `SymbolDetail` extended | B | add `watchers`, `watchers_delta_7d` |
| — | `/screener` extended | C | filter: `most_discussed`, `attention_rising` |

`GET /symbols/{code}/buzz` response (all trend fields `null` until enough snapshot history):

```jsonc
{
  "watchers": 312,
  "watchers_delta_7d": 41,          // null if thin
  "posts_24h": 18,
  "posts_baseline": 6.0,            // trailing N-day avg
  "chatter_x": 3.0,                 // posts_24h / baseline
  "attention": "rising",            // "rising" | "normal" | "quiet" | null
  "reactions_24h": 54,
  "replies_24h": 22
}
```

## 6. Frontend

- **PostCard** ([apps/web/src/components/PostCard.tsx](../../apps/web/src/components/PostCard.tsx)):
  agree/disagree buttons + counts, reply affordance + `reply_count`, expandable thread. No public
  dislike tally framed as negativity — show as "disagree" conviction, not a downvote score.
- **Symbol header** ([Symbol.tsx](../../apps/web/src/pages/Symbol.tsx)): `👁 N watching (+M this
  week)` next to the Watch toggle — delta omitted when thin.
- **Digest** (`/symbols/{code}/digest`, templated): append a thresholded, bilingual attention
  clause only when it clears baseline+floor, e.g. EN *"Discussion is running ~3× heavier than
  usual; watchers up this week."* / BN equivalent. Server-side, templated (same discipline as the
  rebuilt digest — no LLM).
- **Screener**: "most-discussed today" / "attention rising" as descriptive filters.

## 7. Computation: baseline & thresholds (anti-noise)

- **Chatter ratio** = `posts_24h / trailing_baseline` where baseline = mean of the prior N days
  (N≈7–14) from `ticker_buzz_daily`. Analogous to price relative-volume.
- **attention** = `rising` if `chatter_x ≥ 2.0 AND posts_24h ≥ 5`; `quiet` if `posts_24h == 0`;
  else `normal`. Tunable; start conservative.
- **watchers_delta_7d** shown only if `abs(delta) ≥ 5 AND watchers ≥ 20`.
- Everything below threshold → field is `null`, UI omits it.

## 8. Phasing & acceptance criteria

**Phase A — Conviction (reactions + replies). ✅ IMPLEMENTED 2026-06-25.** *Highest retail value,
no new infra.*
- `post_reactions` model + migration (`41a90e2a5dc4`); `POST`/`DELETE /posts/{id}/react`;
  `GET /posts/{id}/replies`; `GET /posts/top`; feed is root-only and returns `reply_count`,
  `agree`, `disagree`, `my_reaction` (via a new `OptionalUser` dep). PostCard shows agree/disagree
  + expandable replies; reply composer (`Composer` compact mode); "🔥 Most discussed" on the symbol
  page. Tests in `test_social.py` cover react→switch→unreact and reply threading.
- *Done:* one reaction per user enforced by composite PK; switching stance upserts; replies
  excluded from the root feed.

**Phase B — Attention snapshot + trend.**
- `ticker_buzz_daily` + EOD job (next to `TickerAnalytics` compute); `/symbols/{code}/buzz`;
  watchers count + 7-day delta on header.
- *Done when:* buzz endpoint returns thresholded fields; trend fields are `null` until ≥N days of
  snapshots exist (verified); header shows watchers with delta omitted when thin.

**Phase C — Synthesis.**
- Templated attention clause folded into the digest (bilingual, thresholded); screener filters
  `most_discussed` / `attention_rising`.
- *Done when:* digest clause appears only above threshold; screener filters return sensible sets;
  no advice/causal language (copy review).

**Phase D — Internal view tracking (optional).**
- `page_view_events` + aggregation into `unique_viewers_24h`; used only as a deweighted buzz input
  and internal analytics. *Never* a standalone user-facing "views" metric.

## 9. Open questions / decisions needed

1. **Reaction semantics:** agree/disagree (conviction on the post) vs an explicit bull/bear vote
   (which could weight crowd sentiment in trending/digest). Recommendation: agree/disagree now;
   revisit feeding it into sentiment weighting in Phase C.
2. **Does conviction reweight sentiment?** e.g. a heavily-agreed bull post counts more in the
   crowd lean. Powerful but adds complexity + gaming surface — defer to a Phase C decision.
3. **View tracking privacy:** anonymous session hash vs user id; retention. Internal-only eases
   this. Confirm we even want Phase D.
4. **Threshold tuning:** the 2×/5-post/7-day numbers are starting guesses; revisit with real data.

## 10. Related cleanup (out of scope, noted)

**Today's Watch** ([trending.py](../../services/api/src/api/routers/trending.py)) still generates
its blurb with an LLM (`todays_watch`) — same mistranslation/garble risk we removed from the
digest. Should be templated the same way in a follow-up.
