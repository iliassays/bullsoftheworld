# systemd units (production server)

These run on the bullstreetai server. They are **not** auto-deployed by `deploy.sh` — install them
by hand once (or after a server rebuild). They live here so the config is version-controlled.

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
sudo cp infra/systemd/bullsofdhaka-worker.service infra/systemd/bulls-ai-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bullsofdhaka-worker bulls-ai-worker
```

Official U.S. regulatory data runs independently from licensed/third-party market-data workers:

```bash
sudo cp infra/systemd/bullsofwallst-sec-worker.service \
  infra/systemd/bullsofwallst-sec-watchdog.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bullsofwallst-sec-worker bullsofwallst-sec-watchdog.timer
```

The SEC watchdog has its own six-hour alert cooldown and checks worker/API liveness, daily EDGAR
freshness, weekly 13F freshness, 8-quarter history depth, refresh failures, and ready-universe
coverage. Set `WALLST_ALERT_EMAIL` to route these separately; otherwise it uses `ALERT_EMAIL` and
then `SUPPORT_EMAIL`. It restarts only an inactive SEC worker and never touches DSE services.

`bullsofwallst-worker.service` is deliberately not included above. Install and enable it only after
the US market-data license, same-site API hostname, verified exchange calendar, and initial cohort
coverage checks in `docs/architecture/multi-tenant-us-readiness.md` are complete.
