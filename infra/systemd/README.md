# systemd units (production server)

These run on the production application host and live here so their configuration is version-controlled.
`deploy.sh` refreshes the active U.S. worker units on every release; the commands below remain the
server-bootstrap procedure and cover the independent DSE watchdog units too.

## Database roles and tenant RLS

Production services must connect with the restricted `bulls_app` role. The database owner is only
for Alembic and role provisioning; never put its URL in the application `.env` or a systemd unit.

1. On the first RLS-aware release, `deploy.sh` runs `scripts/bootstrap_runtime_db_credentials.py`.
   It generates a random runtime password, atomically changes the repository `.env` to `bulls_app`,
   and moves the existing owner URL into `/home/ubuntu/.config/bulls/migration.env` with mode 0600.
   The script refuses to overwrite an existing secret file and never prints credentials.
2. Subsequent releases reuse that deployment-only file. You may instead prepare it manually from
   `.env.migration.example`; keep `MIGRATION_DATABASE_URL` out of the application `.env`.
3. The deploy then runs Alembic as owner, reapplies least-privilege grants, validates the runtime
   credential by connecting as `bulls_app`, and only then restarts services.

API and worker startup checks reject any production role with `SUPERUSER` or `BYPASSRLS`. Tenant
context is transaction-local, so pooled connections cannot retain the preceding request's tenant.

## Health watchdog

`bullsofdhaka-watchdog.{service,timer}` run `ingestion.watchdog` every 5 minutes, **independent of
the arq worker**, so a dead or crash-looping worker can't take its own monitor down. It checks worker
liveness, quote freshness during trading hours, and API `/ready`; on a fault it restarts the worker
once and emails an alert via Resend (Redis-cooldown'd to once per hour).

Install / update:

```bash
sudo cp infra/systemd/bullsofdhaka-watchdog.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bullsofdhaka-watchdog.timer
```

Requires `ALERT_EMAIL` in `/home/ubuntu/bullsofdhaka/.env` (comma-separated recipients; falls back to
`SUPPORT_EMAIL`). The service runs as root so it can `systemctl restart bullsofdhaka-worker`.

## Workers

The three arq workers use separate Redis queues. Install the DSE and AI workers with:

```bash
sudo cp infra/systemd/bullsofdhaka-worker.service /etc/systemd/system/
sudo cp infra/systemd/bulls-ai-worker.service /etc/systemd/system/bullsofdhaka-ai-worker.service
sudo systemctl daemon-reload
sudo systemctl enable --now bullsofdhaka-worker bullsofdhaka-ai-worker
```

Official U.S. regulatory data runs independently from the EOD market-data worker:

```bash
sudo cp infra/systemd/bullsofwallst-sec-worker.service \
  infra/systemd/bullsofwallst-sec-watchdog.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bullsofwallst-sec-worker bullsofwallst-sec-watchdog.timer
```

Install the isolated on-demand preparation worker independently of the licensed EOD publication
worker:

```bash
sudo cp infra/systemd/bullsofwallst-research-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bullsofwallst-research-worker
```

It has no cron schedule, processes one explicit authenticated request at a time, and never promotes
a prepared symbol. Public visibility still requires the normal risk-review and market-data gates.

Atlas lifecycle jobs use a separate worker and queue. Every job carries one exact
tenant/market/user/workspace identity, binds the normal research RLS context, and schedules its own
next verified post-close session only while that workspace policy remains enabled:

```bash
sudo cp infra/systemd/bulls-research-lifecycle-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bulls-research-lifecycle-worker
```

Private U.S. cohort staging runs as a resource-bounded nightly oneshot and never publishes a
cohort. The timer advances to the first unfinished cohort and stops before protected market
windows:

```bash
sudo cp infra/systemd/bullsofwallst-cohort-staging.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bullsofwallst-cohort-staging.timer
```

For an audited first production run, configure exactly one tenant account. The command requires
the tenant, handle, market-registered strategy, paper capital, and an explicit mutation flag; it
does not scan or configure other accounts:

```bash
uv run python scripts/configure_research_lifecycle.py \
  --tenant bullsofdhaka --handle YOUR_HANDLE \
  --strategy-key dse_reversal_v1 --initial-capital 10000000 \
  --enable --dispatch-now --apply
```

The SEC watchdog has its own six-hour alert cooldown and checks worker/API liveness, daily EDGAR
freshness, weekly 13F freshness, 8-quarter history depth, refresh failures, and ready-universe
coverage. Set `WALLST_ALERT_EMAIL` to route these separately; otherwise it uses `ALERT_EMAIL` and
then `SUPPORT_EMAIL`. It restarts only an inactive SEC worker and never touches DSE services.

The SEC and AI units run at lower CPU/I/O weight with bounded memory. The SEC worker also discards
jobs cancelled by a deployment instead of replaying archive work at the next process startup;
freshness monitoring surfaces the missed run and the normal cron schedule retries it.

Run a full on-demand EDGAR and 13F refresh only through its bounded unit. A fixed unit name makes
overlapping runs impossible, while CPU, memory, and wall-clock limits protect the shared APIs:

```bash
sudo cp infra/systemd/bullsofwallst-sec-refresh.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start bullsofwallst-sec-refresh.service
journalctl -u bullsofwallst-sec-refresh.service -f -o cat
```

Do not launch `ingestion.us_sec_refresh --13f` with `nohup`; that bypasses the production resource
contract and leaves no reliable unit state for operations or watchdogs.

The U.S. EOD worker is now an active production unit. On a new server, install it after the provider,
same-site API hostname, verified exchange calendar, and initial coverage checks in
`docs/architecture/multi-tenant-us-readiness.md` are complete:

```bash
sudo cp infra/systemd/bullsofwallst-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bullsofwallst-worker
```
