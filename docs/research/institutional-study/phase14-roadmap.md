# Phase 14 — Implementation Roadmap

**Date:** 2026-07-19. Sequenced so that each stage produces value even if the next never happens,
and so that no capital decision precedes its evidence. This roadmap does not modify the Atlas
mandate's "Next implementation order" for DSE — it defines the US-evidence track that runs beside
it. Wall-clock pacing is deliberately unhurried: the study's documented survivors are the patient
ones, and the mandate forbids optimizing for activity.

## Stage 0 — Infrastructure (prerequisite for everything)

1. **EDGAR ingestion pipeline** (System A's spine, useful to every future system): daily-index
   poller → 13D/G + Form 4 XML parsers → point-in-time archive (append-only; we become our own
   restatement-proof vendor per §13.1.4). Endpoints and rate limits verified live in Phase 8.
2. **Corporate-actions/event calendar** capture (System B's spine) from official sources,
   timestamped at capture.
3. **Cost observatory:** per-name spread measurement over the candidate universes — the 13.2
   cost model needs measured, not assumed, half-spreads. Cheap to build; reusable everywhere.
4. **Experiment harness:** immutable-spec format, trial logging, deflated-statistic reporting,
   override log (13.3–13.4). One harness, all systems.

**Stage-0 exit test:** replay any past week's filings from our own archive byte-identically.

## Stage 1 — Historical diagnostics (paper, backward)

- Run Systems A/B/C through the 13.x protocol on their reconstructible histories. Expected
  per the evidence: System A's follower-capturable share is the genuine open question; System B
  will be episodic and thin (that is not failure — abstention is a result); System C will
  struggle to beat its nulls (that is the point of running it honestly).
- Deliverable per system: the full preregistered report incl. all attempted variants, or a
  data-blocked verdict with the specific missing dataset named (the mandate's pattern).

## Stage 2 — Forward shadow (paper, forward)

- Only systems whose Stage-1 report survives review enter forward shadow; maximum concurrent
  shadow books capped (three, mirroring the mandate's DSE bound — the bound is the point, not
  the number).
- Duration: the mandate's ≥60 sessions/≥10 executions is a *floor*; event books likely need
  12–24 months for statistical honesty given event arrival rates (documented in Stage 1).
- The Phase 15 risk grammar runs live-in-paper from day one — the ladder is being tested as
  much as the signals are.

## Stage 3 — Promotion decisions

- Per 13.5. Note explicitly: **promotion means eligibility, not deployment** (mandate). Any
  live-capital decision is the owner's, made outside this study, with the study's evidence file
  in hand.

## Stage 4 — The standing loop (what "done" looks like)

- Quarterly: re-run decay checks (are the anomalies still there in the forward data?), review
  override log, update the ledger with any new primary evidence (rule changes, new academic
  re-tests — the Phase 8 open questions especially).
- Annually: red-team pass over the live experiment set (Phase 16's checklist, reused);
  post-mortem file per killed or drifting system. The reform cycle is planned for (Phase 11.A.3)
  rather than improvised after the first catastrophe.

## Dependency notes

- Stage 0.1 (EDGAR pipeline) is the highest-leverage single artifact: it feeds System A, the
  squeeze/holder research elsewhere in the portfolio (with Phase 8 §8.1's caveats), and any
  future 13F-based work — build it first.
- Nothing in Stages 0–2 requires paid data. The first paid-data decision (point-in-time
  fundamentals for System C at full rigor) is deferred until System C survives its cheap
  approximation; if it can't beat the null with free data, it won't with expensive data.

## Implementation checkpoint — Atlas engine v2

The current code status is maintained in `implementation-status.md`. Systems A1/A2 and C now run
as registered diagnostics through one execution, cost, risk, null-model, and shadow harness.
System B is deliberately data-blocked. None of the three is a validated edge while the failed
gates listed in that status file remain.
