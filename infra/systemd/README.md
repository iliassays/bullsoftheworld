# systemd units (production server)

These run on the bullstreetai server. They are **not** auto-deployed by `deploy.sh` — install them
by hand once (or after a server rebuild). They live here so the config is version-controlled.

## Health watchdog

`bullsofdhaka-watchdog.{service,timer}` run `ingestion.watchdog` every 5 minutes, **independent of
the arq worker**, so a dead or crash-looping worker can't take its own monitor down. It checks worker
liveness, quote freshness during trading hours, and API `/health`; on a fault it restarts the worker
once and emails an alert via Resend (Redis-cooldown'd to once per hour).

Install / update:

```bash
sudo cp infra/systemd/bullsofdhaka-watchdog.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bullsofdhaka-watchdog.timer
```

Requires `ALERT_EMAIL` in `/home/ubuntu/bullsofdhaka/.env` (comma-separated recipients; falls back to
`SUPPORT_EMAIL`). The service runs as root so it can `systemctl restart bullsofdhaka-worker`.

> The pre-existing `bullsofdhaka-worker.service` (arq cron) is also server-only; capture it here too
> if it ever changes.
