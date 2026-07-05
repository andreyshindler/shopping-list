# Auto-deploy (pull-based)

`main` auto-deploys to the VPS, but the VPS **pulls** — GitHub does not SSH in.
This avoids the fragile inbound-SSH path (fail2ban would silently DROP the GitHub
runner's rotating IPs, so deploys timed out at random).

## How it works

[`scripts/auto_deploy.sh`](../scripts/auto_deploy.sh) runs from host cron every
minute:

1. `git fetch origin main`; if `HEAD` already equals `origin/main`, exit (no-op).
2. Otherwise `git reset --hard origin/main`, then `docker compose up -d --build`
   and `docker image prune -f`.
3. Ping the admin on Telegram (✅/❌) using `BOT_TOKEN` + `ADMIN_TELEGRAM_ID`
   from `.env`. **On failure the full `docker compose … --build` output is
   attached as a file** so you can debug without SSHing in.

A `flock` guard means a build that runs longer than a minute won't overlap the
next tick. Override the branch with `DEPLOY_BRANCH` if needed.

## One-time setup on the VPS

```bash
cd ~/projects/shopping-list
bash scripts/install-auto-deploy-cron.sh
```

That installs (idempotently):

```cron
* * * * *  /home/komodo/projects/shopping-list/scripts/auto_deploy.sh >> /home/komodo/projects/shopping-list/auto-deploy.log 2>&1
```

Tune the cadence with `AUTO_DEPLOY_SCHEDULE` (e.g. `*/2 * * * *`) and the log path
with `AUTO_DEPLOY_LOG` (defaults under the repo dir so the deploy user can write it
without `sudo`).

## Deploy / check

- Merge to `main` → the VPS picks it up within ~1 minute and rebuilds.
- Watch it: `tail -n 40 auto-deploy.log`
- Force one now: `bash scripts/auto_deploy.sh`

The old `.github/workflows/deploy.yml` (SSH-in) has been removed. The `price-fetch`
job is a separate host cron; see [price-fetch-cron.md](price-fetch-cron.md).
