# Spec: Feed Moderation — the compliance gate (কনটেন্ট মডারেশন)

Status: **draft for review** · Owner: Ilias · Layer: new `packages/moderation` + `api` write-path
hook + `ai_worker` escalation · Last edit 2026-07-01 (Ilias + Codex + Claude)

---

## 1. Problem & intent

Our feed carries **public, user-written posts** about a **heavily regulated** market (DSE / BSEC).
Unmoderated, that is a liability: pump-and-dump recruiting, unlicensed "buy X, target ৳Y" advice,
guaranteed-return scams, rumour-as-fact price-sensitive claims, off-platform tip-group solicitation,
and plain abuse. Our whole brand is **"Facts, not rumours"** and **descriptive-only** — moderation is
not a feature bolted on, it *is* the moat.

Two hard constraints shape the design:

1. **We cannot afford an LLM call per post.** At any real volume, sending every post to Claude is both
   too expensive and too slow for the write path. Claude must be the *last* resort on a *tiny* residual,
   not the front door.
2. **Moderation must not slow the post request, but risky market content must not go public first.**
   Core principle #1: AI never blocks a web request. The synchronous write path may only run cheap,
   local, deterministic checks; anything heavier runs async in `ai_worker` via the queue. However,
   DSE/BSEC-sensitive gray-zone content is saved as `pending` and visible only to the author until
   cleared. It is not published publicly with reduced reach.

**Goal:** a layered pipeline where **free deterministic rules resolve the overwhelming majority**,
cheap embeddings catch paraphrases, and an LLM adjudicates only the uncertain residual —
budget-capped, async, cached. It must work end-to-end **with zero AI** (Phase 1); AI only sharpens the
review queue later. Generic moderation vendors can help with abuse/safety, but the core DSE
manipulation detector must be our own rules/features because off-the-shelf tools do not understand
Bangla/Banglish stock manipulation well enough.

---

## 2. Principles & guardrails (non-negotiable)

1. **Cost descends down the cascade.** Every post enters at Layer 0. It exits as soon as a cheaper layer
   is confident. A post only reaches Claude if Layers 0–3 all abstained *and* it has real reach.
2. **AI is a layer, never the foundation.** Layers 0–2 ship first and are complete on their own. If the
   AI budget is exhausted or the worker is down, the system degrades gracefully: gray-zone posts stay
   `pending`/hidden from public feeds, never fail open to a pump post going viral.
3. **The write path stays fast and local.** Synchronous check = Layers 0–2 only, target **< 15 ms**, no
   network. Clear violations are rejected at write; clear safe content publishes; DSE/BSEC-sensitive
   ambiguity is stored as `pending` and reviewed async.
4. **Over-blocking is the primary failure, not under-blocking.** Wrongly gagging a real user kills the
   community. Default to **LABEL / HOLD** for ambiguity; reserve hard **BLOCK** for unambiguous
   violations; always give the user a reason and an appeal path.
5. **Omit over mislead, descriptive over prescriptive.** A rumoured price-sensitive claim is not
   published unless it matches an official DSE/company announcement already in our data. Otherwise it
   is held for review. "Unverified" labels are only for already-cleared low-risk discussion, not for
   raw price-sensitive claims.
6. **Tenant-agnostic core.** The engine is generic. Lexicons, patterns and thresholds are **per-tenant
   config** (`tenants/<name>/moderation/`). Dhaka ships Bangla + Banglish (romanized) + English; a future
   tenant ships its own. Nothing DSE/Bangla-specific is hard-coded in `bulls.moderation`.
7. **Every decision is auditable.** Immutable `moderation_events` log: which layer decided, why (rule ids
   / categories / score), and — for Layer 4 — the model, tokens and cost. Never fake, never silent.
8. **Right tool per job.** Manipulation/pump detection is a **classic-ML / rules** problem (features +
   velocity + near-duplicate), *not* an LLM problem. The LLM only handles genuine natural-language
   ambiguity.
9. **Relevance is a risk *signal*, not a hard gate.** Off-topic content reduces feed quality and gives
   manipulators cover, so it *raises* the L2 risk score and can tip a post into HOLD **only when combined
   with other manipulation signals** — it is never blocked on its own. Deterministic "does it mention the
   route ticker?" is too crude: legit replies often don't restate the cashtag, and `$GP`-vs-`$ROBI`
   comparisons are valid. The one relevance case hard enough to gate is identical text sprayed across many
   unrelated symbols — and L2 near-duplicate already catches that.

---

## 3. Violation taxonomy (what we are actually filtering)

BSEC-aligned categories, each with a default action. Actions defined in §5.

| # | Category | Example (EN / Banglish) | Default action |
|---|---|---|---|
| C1 | **Investment advice / recommendation** | "buy $GP now", "sell before close", "target ৳120" / "akhon kinen", "beche den" | HOLD; severe target/advice = BLOCK |
| C2 | **Guaranteed return** | "guaranteed 20% profit", "sure return", "no loss" / "100% profit", "loss hobe na" | BLOCK |
| C3 | **Pump / coordinated manipulation** | "everyone buy at open", "syndicate loading", "circuit lagbe kalke", "load koro" | BLOCK / HOLD |
| C4 | **Rumour as fact (price-sensitive)** | "dividend confirmed", "merger next week", "bonus 1:1 pakka" | HOLD unless verified against official announcement |
| C5 | **Off-platform solicitation / paid tips** | telegram/whatsapp links, "DM for tips", "join my signal group" | BLOCK by default; HOLD if ambiguous |
| C6 | **Abuse / profanity / harassment** | slurs, threats (Bangla + Banglish + English) | MASK / BLOCK |
| C7 | **Insider-information claim** | "my source at the company says…", "insset khobor ache" | HOLD |
| C8 | **Impersonation of an official desk** | posing as `@BullsOfDhaka*` / an authority | BLOCK (ties to `User.is_official`) |
| C9 | **Irrelevant / spam / low-quality** | unrelated politics, crypto promo, repeated emojis, same post on many stocks | HOLD / BLOCK after repeat |

C1/C3/C4 are the regulatory core; C6 is community hygiene; C5/C7/C8 are the scam/fraud vectors.

---

## 4. The cascade (cost-descending pipeline)

```
POST /posts  ──► [ SYNCHRONOUS, local, < 15ms, zero AI ]
  L0  Normalize & extract      (deobfuscate, Bangla + Banglish fold, pull cashtags/numbers/links)
  L1  Deterministic gates      (lexicon + regex → category + severity)   ~free
  L2  Heuristic risk score     (features + velocity + near-dup)          ~free
        │
        ├─ clear BLOCK  ─────────────► reject at write (HTTP 422 + reason)   [C2/C3/C8 severe]
        ├─ clear ALLOW  ─────────────► publish normally
        └─ GRAY ZONE    ─────────────► save as `pending` (author-visible only; not public)
                                        └─► enqueue_moderation(post_id)     [ASYNC, ai_worker]

[ ASYNC in ai_worker, never on the request ]
  L3  Semantic near-neighbour  (embed post → pgvector vs curated violation exemplars)   cheap, cached
        ├─ confident ───────────────► finalize (ALLOW / LABEL / HOLD / BLOCK)
        └─ still uncertain AND high-reach ─► L4
  L4  LLM adjudication                  budget-capped · batched · hash-cached · sampled
        └─────────────────────────────► finalize + write moderation_event
```

### L0 — Normalize & extract (the hard, high-leverage part)
Evasion lives here, and **Banglish is where naive filters fail**. Steps:
- Unicode NFKC normalize; strip zero-width / combining tricks; collapse repeated chars (`buuuy`→`buy`).
- De-leet / de-space obfuscation (`b.u.y`, `b u y`, `8uy`, `ki ne n`).
- Produce **three views**: raw, Bangla-normalized, and a **romanized/transliterated** view so a single
  Banglish lexicon matches `kinen`/`kinun`/`kena`.
- Extract structured signals: cashtags (reuse `parse_cashtags`), **numbers with money/percent context**
  (target-price / return patterns), URLs, phone numbers, messaging-app handles.
- Extract thread context: route stock code, parent post code, global vs symbol feed, and whether the
  body is relevant to the requested stock.

This module is the single biggest determinant of quality. It gets its own tests and its own eval slice.

### L1 — Deterministic gates (lexicon + regex), free
Per-tenant config files → compiled matchers. Each entry: `pattern | category | severity | action`.
- **Profanity/abuse lexicon** (Bangla + Banglish + English) → MASK (mild) or BLOCK (slurs/threats).
- **Regulatory phrase patterns**: advice verbs + cashtag (`(buy|sell|kinen|bechen)\s+\$?[A-Z]{2,}`),
  price targets (`target\s*৳?\d+`), guarantees (`guaranteed|sure profit|no loss|100%`), pump
  (`everyone buy|load koro|circuit`), solicitation (telegram/whatsapp/`DM`/phone).
- **Cross-symbol spam gate:** identical/near-identical text tagging many unrelated symbols is held —
  the one relevance case deterministic enough to gate here (softer relevance is an L2 signal, §L2).
- **Announcement verification gate:** price-sensitive claims ("dividend confirmed", "rights", "merger",
  "bonus", "EPS leak") must match a recent official announcement in our DB before public display. Match
  **coarsely** — code + announcement `category` + recency (a `dividend` claim on a code with a `dividend`
  row in the last N days), *not* exact-value verification. Until that matcher ships, these claims are
  always-HOLD (fine for Phase 1; it loads the queue).
- Deterministic and explainable → the fastest, cheapest, most defensible layer. Most bad posts die here.

### L2 — Heuristic risk score (classic ML, free)
For posts L1 didn't settle, compute a manipulation score from cheap features — **no model API**:
- **Content features:** cashtag × directional verb × price-target × urgency × solicitation present.
- **Account trust:** account age, verified/`is_official`, prior violation count, follower/history.
- **Velocity:** same author spamming the same cashtag; sudden burst on one thinly-traded code.
- **Near-duplicate:** SimHash/MinHash vs recent posts → **coordinated pump** (many accounts, same text).
- **Relevance signal:** a post routed to a symbol page but not plausibly about it (no route cashtag, low
  term overlap) raises the score — a soft input, never a standalone block (see principle #9).
- **Market-risk context:** thin liquidity, Z category, extreme move/circuit proximity, and new-account
  bursts raise the risk score because those are easier to manipulate.
- Combine via a small **logistic-regression / gradient-boosted** classifier (or a transparent weighted
  rule set in Phase 1) → `risk ∈ [0,1]` + contributing categories. Thresholds set the ALLOW / gray /
  BLOCK bands. Retrainable from review-queue outcomes.

### L3 — Semantic near-neighbour (cheap, async)
Reuses the **pgvector** infra already in `bulls.ai.retrieval`. Maintain a curated, growing set of
**violation exemplars** (real held/blocked posts + synthetic), embedded once. For a gray-zone post:
embed it (cheap; cache by content hash), find nearest exemplars; high similarity to a category cluster →
finalize with that category. Catches paraphrases and novel Banglish the lexicon misses, **without any
generative call**. Embedding cost is a fraction of generation and fully cacheable.

### L4 — LLM adjudication (Claude Haiku, last resort)
The DSE-domain judgment (C1/C3/C4/C7) is *multilingual reasoning*, which generic safety APIs cannot do —
so L4 is **one reasoning model, Claude Haiku**: strong on Bangla/Banglish, cheap, already our stack (one
vendor, one eval harness, the `/claude-api` guidance). A *second* reasoning LLM for adjudication would
double eval/ops/vendor surface for no real gain; cost isn't the concern because L4 volume is tiny.

Only when **L0–L3 all abstained AND the post has real reach** (verified author, high followers, or a
trending/liquid cashtag — a nobody's ambiguous post can wait in `pending`, it isn't worth a token).
- Runs in `ai_worker`, **never on the request** (principle #1).
- **Budget-capped** (daily token ceiling; when hit, new gray-zone posts stay `pending`/limited-reach
  instead of being adjudicated — graceful degradation, never fail-open).
- **Batched** (adjudicate several queued posts per call) and **cached by normalized-content hash** (a
  re-posted pump text is a cache hit, not a new call).
- Prompt is a **strict classifier** returning `{category, action, confidence, reason}` against the §3
  taxonomy — descriptive-only, no free-form generation.
- Output feeds back as new L3 exemplars, so the cheap layer keeps getting smarter and L4 volume trends
  down over time.

### External provider fit (useful, but not the core)

- **OpenAI Moderation API**: useful as an async helper for generic safety/toxicity/self-harm/abuse.
  It should not decide DSE manipulation alone because financial-advice, Bangla/Banglish pump language,
  and rumor verification are domain-specific.
- **AWS Comprehend Toxicity**: not a good core fit because toxicity detection is English-only in the
  documented product. It can miss Bangla/Banglish abuse.
- **Azure AI Content Safety**: usable for generic safety and possibly custom categories, but custom
  financial manipulation still needs our own rules/evals. Treat as optional Phase 3 support, not a
  Phase 1 dependency.
- **Perspective API**: useful for toxicity in supported languages, but it is community-safety oriented,
  not financial manipulation or DSE rumor verification.

**One caveat that governs all four:** they underperform badly on **Banglish (romanized Bangla)**, and
Comprehend is English-only outright — so the **local L1 Banglish lexicon stays the primary C6 filter**;
a safety API is only a free async backstop, never allowed to *decide* manipulation (which it can't judge).

The recommended stack is therefore: **local deterministic moderation + Redis/Postgres velocity checks
+ SimHash/MinHash near-duplicate + pgvector exemplars + Claude Haiku for the tiny DSE-domain adjudication
residual, with OpenAI's free Moderation API as an async C6 safety backstop only**.

---

## 5. Decision vocabulary & write-path policy

| Action | Effect |
|---|---|
| **ALLOW** | Publish normally. |
| **MASK** | Publish with profanity masked (`****`); logged. |
| **LABEL** | Publish with a banner only after content is cleared as low-risk — e.g. *"Opinion, not advice"* or *"Unverified discussion"*. Not for raw price-sensitive claims. |
| **HOLD** | Not shown publicly; queued for review (or async adjudication). Author sees "under review". |
| **BLOCK** | Rejected. Author sees the category reason and an appeal link. |

**Sync vs async split (critical):**
- **Hard-block clear violations synchronously** (C2 guarantee, severe C3 pump, C5 solicitation, C8
  impersonation, threats/slurs).
  A live pump post for even two minutes does damage — these die at write with HTTP 422 + reason.
- **Clear-allow publishes normally.**
- **Gray zone is saved as `pending`, author-visible only** — not public, not searchable, not in symbol
  feed, Home, trending, notifications, digest, or FB surfacing until cleared. This is stricter than
  publish-with-reduced-reach because market manipulation risk is not worth the UX benefit.
- **Keep the gray band deliberately tight.** Because `pending` = invisible to everyone but the author,
  borderline-*benign* must resolve to ALLOW, not `pending` — otherwise the feed feels dead and honest
  users feel silently shadowbanned, which kills the very growth we want. `pending` needs: (a) a
  dwell-time **SLA + auto-expire** (never auto-publish a held post — expire to hidden), and (b) explicit
  **"under review, usually < N hrs"** UX so it never reads as silent censorship.
- **Rumor-as-fact is HOLD-first.** The only way a price-sensitive claim becomes public without human
  review is if it matches an official DSE/company announcement already stored in our announcements
  table; otherwise it waits.
- **Fail-open policy:** if the async engine errors, the post stays `pending`/hidden — never
  auto-promoted. The local L1 hard-block always applies (it can't fail; no network).

---

## 6. Data model & placement

**New package `packages/moderation` (`bulls.moderation`)** — tenant-agnostic, zero AI:
`normalize.py`, `lexicon.py` (config loader), `rules.py` (L1), `scorer.py` (L2), `engine.py`
(orchestrates L0–L2 + returns a `Decision`), `exemplars.py` (L3 helpers over pgvector).
**LLM adjudicator lives in `packages/ai`** (`bulls.ai.tasks.moderation`, runs in `ai_worker`) so the
core engine has no AI dependency.

**Migrations (Alembic):**
- `Post.moderation_status`: `published | pending | held | blocked` (server default `published` for the
  fast path). Do **not** rely on `limited_reach` for DSE-sensitive gray zone; pending posts are hidden
  from public surfaces.
- `Post.moderation_reason`: short user-facing reason code/message (`advice_target`, `rumor_unverified`,
  `solicitation`, `spam_relevance`, etc.) so the client can explain what happened.
- `Post.normalized_hash`: content hash after L0 normalization for repost/duplicate blocking.
- **`moderation_events`** (append-only audit): `id, post_id, tenant_id, decision, layer(0–4),
  risk_score, categories(JSON), rule_ids(JSON), model, tokens, cost, latency_ms, actor(system|reviewer),
  note, created_at`.
- Feed reads (`posts.feed`, replies, top post, digest, pulse, buzz, trending, FB surfacing) filter to
  `moderation_status='published'`.

**Per-tenant config** `tenants/dhaka/moderation/`: `profanity.{bn,banglish,en}.txt`,
`regulatory_patterns.yml`, `relevance.yml`, `solicitation.yml`, `thresholds.yml`, `exemplars.jsonl`.
Hot-reloadable; changes are config, not code.

**Hook point:** `create_post` ([posts.py:152](services/api/src/api/routers/posts.py:152)) — run
`engine.decide(body, route_code, parent_id, user_context)` before public visibility is granted; set
`moderation_status`; on hard BLOCK raise 422; on gray zone save pending and `enqueue_moderation(post.id)`
right after the existing `enqueue_sentiment` pattern.

**Review queue:** an admin endpoint listing `pending`/`held` with the event trail, category, matched
rules, normalized text, source route, cashtags, account age, previous violations, and latest official
announcement matches. A human (Ilias initially) approves/blocks; outcomes retrain L2 and seed L3
exemplars. Small and simple for Phase 1.

---

## 7. Cost model (why this is affordable)

Illustrative at **1,000 posts/day**:

| Layer | Share resolved | Unit cost | Daily cost |
|---|---|---|---|
| L0–L2 (deterministic) | ~90–95% | free | **৳0** |
| L3 (embeddings, cached) | most of the rest | ~fraction of a paisa, cache-heavy | pennies |
| L4 (LLM / external moderation) | **~1–3% residual**, batched + hash-cached | small classifier call | **cents/day** |

Versus "Claude on every post" (1,000 calls/day) this is a **~30–50× reduction**, and it's **bounded** —
the L4 budget cap is a hard ceiling, and the more L4 runs, the more exemplars L3 gains, so L4 volume
*falls* over time. Scaling to 10× traffic scales the free layers linearly and the LLM cost sub-linearly
(cache hit-rate rises with volume).

---

## 8. Evals (no AI ships without a labelled set — CLAUDE.md step 4)

- **Golden set**: hand-labelled posts spanning all §3 categories × {Bangla, Banglish, English} ×
  {obvious, obfuscated, benign-lookalike}. Include hard **false-positive traps** (legit posts that
  mention "target" or a cashtag descriptively) — over-blocking is the metric we most fear.
- **Metrics**: per-category precision/recall, **overall false-positive (over-block) rate**, pending
  queue size/SLA, L4 escalation rate, and cost per 1k posts. Gate: precision on hard-BLOCK categories
  high enough that we're comfortable auto-rejecting; recall on C1–C5 above target; FP rate under a
  strict ceiling.
- **Relevance eval:** posts routed to a symbol page must be about that symbol unless replying in a
  broader thread. Include false-positive traps such as comparing `$GP` with `$ROBI` legitimately.
- **Rumor verification eval:** claims about dividend, bonus, merger, rights, EPS, price-sensitive
  announcements must be held unless a matching announcement exists.
- **Regression**: the eval runs in CI on any lexicon/threshold/prompt change. L4 gets its own prompt
  eval harness (like `sentiment`).

---

## 9. Phasing

- **Phase 1 — deterministic core, zero AI (ships the moat).** `bulls.moderation` L0–L2 + normalization +
  Bangla/Banglish/English lexicons + relevance gate + rumor verification gate + solicitation blocking +
  migrations + write-path gate + review queue + the golden eval set. This alone catches the large
  majority and is fully defensible to a regulator.
- **Phase 2 — cheap semantic (L3).** pgvector exemplars over the growing review-queue corpus.
- **Phase 3 — external/LLM escalation (L4).** Optional OpenAI Moderation for generic safety and/or a
  strict classifier LLM in `ai_worker`, budget-capped + cached + batched, plus threshold auto-tuning
  from review outcomes and the exemplar feedback loop.

Each phase is independently shippable and each raises quality without touching the write-path budget.

---

## 10. Open questions (decide before Phase 1)

1. **Reviewer capacity & SLA.** Is Ilias the sole reviewer? What's the acceptable `pending`/`held` dwell
   time before a gray-zone post auto-expires (stays hidden) vs auto-publishes? (Recommend: never
   auto-publish a held post; expire to hidden.)
2. **Gray-zone default.** Recommendation: hold-before-publication for all market-sensitive categories.
   Are there any low-risk categories where author-visible pending is too strict?
3. **Banglish lexicon sourcing.** Seed list origin + who curates ongoing? This is the make-or-break asset.
4. **Appeals.** In-app appeal → review queue, or email? What's the turnaround promise?
5. **Retention.** How long do we keep blocked content + events for audit / potential BSEC inquiry?
6. **Edit & repost.** Re-moderate on edit (yes) — but note **no post-edit endpoint exists today**, so
   this is a future hook, not a Phase 1 item. Repost-dedup via the `normalized_hash` cache applies now.
7. **Legal/data policy.** Confirm retention period and export format for possible DSE/BSEC inquiry.
   Recommend keeping moderation events and blocked content for at least 2 years unless legal counsel
   sets another policy.

---

## 11. References

- CLAUDE.md core principles #1 (AI never blocks), #3 (tenant-agnostic), #6 (right tool: fraud = classic
  ML). Build step 4 (no AI without an eval set).
- `docs/specs/trending-engine.md` — regulatory posture, omit-over-mislead, descriptive-only.
- `docs/research/dse-trading-research.md` — descriptive-only moat rationale.
- Existing patterns to mirror: `enqueue_sentiment` async queue ([posts.py](services/api/src/api/routers/posts.py)),
  pgvector retrieval (`bulls.ai.retrieval`), the sentiment eval harness (`bulls.ai.tasks.sentiment`).
- OpenAI Moderation API — useful optional helper for generic safety, not domain manipulation.
- AWS Comprehend Toxicity — English-only toxicity detection; not suitable as core for Bangla/Banglish.
- Azure AI Content Safety / Perspective API — optional generic safety aids; not substitutes for
  DSE-specific rules, relevance gates, announcement matching and audit logs.
