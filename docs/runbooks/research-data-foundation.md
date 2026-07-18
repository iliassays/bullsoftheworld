# Research data foundation operations

This runbook activates or repairs the immutable research-data foundation on the shared production
host. It does not promote US cohorts, enable an unlicensed dataset, or make a historical backtest
point-in-time complete.

## Safety contract

- Run source baselines and legacy bootstrap jobs sequentially.
- Keep long jobs outside DSE polling/EOD windows and the US EOD chain when possible.
- Use transient systemd units for jobs longer than a few minutes; an SSH disconnect must not stop a
  data transaction.
- Set `Nice`, `CPUQuota`, `MemoryMax`, and a wall-clock limit. Use `RuntimeMaxSec` for transient
  `Type=simple` jobs and `TimeoutStartSec` for repository `Type=oneshot` units. Check API latency
  and host load between stages.
- Never manufacture `published_at` or historical `known_at`. Legacy bars remain
  `knowledge_time_quality=legacy_unknown`.
- Never promote `point_in_time_complete` because a bootstrap finished. That flag requires inactive
  universe, revision, identity, and publication-time evidence.

All commands run from `/home/ubuntu/bullsofdhaka`. The installed `.env` is the runtime credential
source; do not print or copy it.

## Preflight

```bash
git rev-parse --short HEAD
df -h /
free -h
systemctl --failed
systemctl is-active \
  bullsofdhaka-api bullsofdhaka-worker bullsofdhaka-ai-worker \
  bullsofwallst-worker bullsofwallst-sec-worker bullsofwallst-research-worker \
  bulls-research-lifecycle-worker
curl -fsS https://api.bullsofdhaka.com/ready
curl -fsS https://api.bullsofwallst.com/ready
.venv/bin/python -m ingestion.foundation_audit
```

Take the normal database snapshot before a migration or large first-time bootstrap.

Full SEC/13F refreshes use the canonical bounded unit, never an unmanaged background process:

```bash
sudo systemctl start bullsofwallst-sec-refresh.service
systemctl status bullsofwallst-sec-refresh.service --no-pager
tail -f /home/ubuntu/bullsofdhaka/var/log/sec-refresh.log
```

Starting the same unit again cannot create an overlapping run. The parser reports progress every
250,000 holdings rows, atomically checkpoints each provenance-scoped derived archive under
`var/sec-13f-cache`, and deletes the downloaded raw ZIP. A timeout therefore resumes from the last
complete parse instead of rescanning it.

FINRA consolidated NMS short volume is an independent daily feed. The US worker fetches it after
the expected publication window at 23:45 UTC, validates the source trailer and volume invariants,
and catches up missing recent sessions. A high short-marked share is descriptive activity, not
short interest and not a directional trade signal.

US option-chain previews are owner-only, on demand, cached briefly, and not retained as a research
history. Bulk options ingestion remains fail-closed unless a current licensed delivery and its
entitlement metadata are configured. The discontinued Cboe Option Sentiment product must not be
presented as an active source.

## Bounded unit template

Use a unique unit name. This example gives the task one CPU, low scheduler priority, a 3 GiB memory
ceiling, and a 90-minute wall-clock bound:

```bash
sudo systemd-run \
  --unit=bulls-data-foundation-example \
  --collect \
  --property=User=ubuntu \
  --property=WorkingDirectory=/home/ubuntu/bullsofdhaka \
  --property=EnvironmentFile=/home/ubuntu/bullsofdhaka/.env \
  --property=Nice=12 \
  --property=CPUQuota=100% \
  --property=MemoryMax=3G \
  --property=RuntimeMaxSec=90min \
  /home/ubuntu/bullsofdhaka/.venv/bin/python -m ingestion.foundation_audit
```

`TimeoutStartSec` is not a runtime limit for a `Type=simple` unit: systemd considers that unit
started as soon as the process is launched, so transient jobs use `RuntimeMaxSec`. Repository
`Type=oneshot` units remain in their start phase until completion and use `TimeoutStartSec`.

Monitor without attaching to the process:

```bash
systemctl is-active bulls-data-foundation-example.service
journalctl -u bulls-data-foundation-example.service -f -o cat
curl -sS -o /dev/null -w '%{http_code} %{time_total}s\n' \
  https://api.bullsofdhaka.com/ready
```

## Activation order

1. Deploy and migrate.
2. Refresh DSE company/fundamental/ownership data:

   ```bash
   .venv/bin/python -m ingestion.company
   ```

   The weekly ARQ cron has its own 30-minute timeout. A source-absent company is an explicit gap,
   not a reason to invent a profile.

3. Refresh the guarded US security master:

   ```bash
   .venv/bin/python -m ingestion.security_master US
   ```

   The transaction fails before publication on truncated source files, universe collapse, duplicate
   symbols, low CIK coverage, or unresolved identity transfer.

4. Establish SEC filing and Company Facts revision lineage:

   ```bash
   .venv/bin/python -m ingestion.sec
   ```

   If interrupted, update to a release that supports zero-row manifests and resume only missing
   issuer baselines:

   ```bash
   .venv/bin/python -m ingestion.sec --missing-lineage
   ```

   A zero-row accepted source manifest means "checked, no normalized facts". No manifest means
   "not completed". These states must remain distinct.

5. Bootstrap legacy bars one symbol/transaction at a time:

   ```bash
   .venv/bin/python -m ingestion.foundation_bootstrap DSE --all --limit 25 --pause-ms 100
   .venv/bin/python -m ingestion.foundation_bootstrap US --all --limit 25 --pause-ms 100
   ```

   Every progress line prints `next_after`. Resume a timed-out unit with `--after CODE`; completed
   symbol transactions are idempotent.

6. Recompute reproducible current analytics:

   ```bash
   .venv/bin/python -m ingestion.analytics DSE
   .venv/bin/python -m ingestion.analytics US
   ```

7. Run tenant-bound Atlas lineage smoke tests with real owner workspace/user identifiers:

   ```bash
   .venv/bin/python scripts/verify_atlas_lineage.py \
     TENANT MARKET WORKSPACE_UUID USER_ID CODE --commit
   ```

   The command must report at least one claim and citation, and every claim must cite an immutable
   fact span. Run it once per market tenant.

8. Run strict acceptance:

   ```bash
   .venv/bin/python -m ingestion.foundation_audit --strict
   .venv/bin/python -m ingestion.foundation_audit --market US --strict
   ```

## Complete US private catalog

Refresh the guarded security master once, then freeze a deterministic catalog snapshot:

```bash
.venv/bin/python -m ingestion.security_master US
.venv/bin/python -m ingestion.full_universe_catalog
```

The catalog includes every active product-eligible common stock, ADR, and ETF. Its policies are
instrument-specific: ETFs do not require CIK, filings, or Company Facts; ADRs require identity and
filings but not domestic-issuer XBRL facts; common stocks require all applicable SEC evidence.

Advance one cohort manually without redownloading the security master:

```bash
.venv/bin/python -m ingestion.universe_onboarding_batch \
  var/us-full-universe/YYYY-MM-DD/manifest-index.json \
  --max-cohorts 1 --reuse-security-master --continue-on-failure
```

`bullsofwallst-full-universe.timer` continues the latest catalog daily at 09:15 UTC within the
protected runtime budget. Market-closed Saturday catch-up slots at 14:30, 17:00, and 19:30 UTC
accelerate large snapshots without competing with live-session ingestion. The oneshot service and
its two-hour runtime/resource limits make overlapping timer events harmless. Completion means every
active product-eligible catalog symbol is `ready`, `partial`, or `unavailable` in private research
state. It does not mean every instrument has company financials, nor does it grant public display
rights. Strict US acceptance fails while any active product-eligible catalog symbol remains
`reference_only`, `onboarding`, or `degraded`; inactive and product-excluded historical rows remain
auditable but do not block acceptance.

## US cohort backlog

The cap-band cohort runner predates the complete product-eligible catalog. After all full-universe
cohorts reach a terminal state, its persistent timer must remain disabled; running both schedulers
reprocesses the same instruments and makes completion status ambiguous. Keep the legacy service
available only for an explicitly approved diagnostic replay:

```bash
systemctl is-enabled bullsofwallst-cohort-staging.timer  # expected: disabled
systemctl start bullsofwallst-cohort-staging.service     # manual diagnostic only
```

Do not publish a cohort because its acquisition stages completed. Promotion still requires the
manifest's liquidity, identity, history, SEC, marketability, and risk gates. A failed band must not
block independent bands; the next run resumes from the first incomplete cohort in each band.

## Acceptance evidence

Record the release SHA and final counts for:

- ready symbols, latest completed-session coverage, and analytics fingerprints by market;
- daily-bar observation rows and distinct symbols;
- DSE company source manifests and explicit source absences;
- US listing events and identity drift count;
- SEC Company Facts manifests, revisions, failures, and checked-empty issuers;
- onboarding runs by terminal status and the next cohort timer;
- Atlas evidence documents, run-evidence links, spans, claims, citations, and cross-tenant mismatch
  count;
- database size, disk headroom, API readiness latency, and failed systemd units.

The release is operationally usable when critical audit findings are zero. Historical strategy
results remain diagnostic until the separate point-in-time universe and revision gates pass.
