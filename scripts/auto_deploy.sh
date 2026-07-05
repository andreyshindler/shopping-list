#!/usr/bin/env bash
# Pull-based auto-deploy. The VPS checks origin/<branch> and redeploys when it
# moves — no inbound SSH from GitHub, so fail2ban / firewalls can't break deploys.
#
# Install via host cron (see docs/auto-deploy-cron.md):
#   * * * * * /path/to/scripts/auto_deploy.sh >> /var/log/auto-deploy.log 2>&1
set -euo pipefail

REPO_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="${DEPLOY_BRANCH:-main}"
LOCK="/tmp/shopping-list-auto-deploy.lock"

cd "$REPO_PATH"

# Serialize: a build can take longer than the cron interval — skip if one is running.
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "$(date -Is) deploy already in progress, skipping"
  exit 0
fi

git fetch --quiet origin "$BRANCH"
LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse "origin/${BRANCH}")"
[ "$LOCAL" = "$REMOTE" ] && exit 0   # up to date

DOCKER="$(command -v docker)"

# Best-effort Telegram ping to the admin; creds read from .env (no shell sourcing).
notify() {
  local token chat
  token="$(grep -E '^BOT_TOKEN=' .env 2>/dev/null | tail -1 | cut -d= -f2-)"
  chat="$(grep -E '^ADMIN_TELEGRAM_ID=' .env 2>/dev/null | tail -1 | cut -d= -f2-)"
  [ -n "$token" ] && [ -n "$chat" ] || return 0
  curl -s -X POST "https://api.telegram.org/bot${token}/sendMessage" \
    -d chat_id="$chat" --data-urlencode text="$1" >/dev/null 2>&1 || true
}

echo "$(date -Is) deploying ${BRANCH} ${LOCAL:0:7} -> ${REMOTE:0:7}"
git reset --hard "origin/${BRANCH}"
MSG="$(git log -1 --pretty=%s)"

if "$DOCKER" compose up -d --build; then
  "$DOCKER" image prune -f >/dev/null 2>&1 || true
  echo "$(date -Is) deploy OK ${REMOTE:0:7}"
  notify "$(printf '✅ Deployed %s\n%s' "${REMOTE:0:7}" "$MSG")"
else
  echo "$(date -Is) deploy FAILED ${REMOTE:0:7}"
  notify "$(printf '❌ Deploy FAILED %s\n%s' "${REMOTE:0:7}" "$MSG")"
  exit 1
fi
