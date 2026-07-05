#!/usr/bin/env bash
# Install the pull-based auto-deploy cron on the VPS host (idempotent).
# Run once per machine: bash scripts/install-auto-deploy-cron.sh
set -euo pipefail

REPO_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCHEDULE="${AUTO_DEPLOY_SCHEDULE:-* * * * *}"
LOG_FILE="${AUTO_DEPLOY_LOG:-/var/log/auto-deploy.log}"
SCRIPT="${REPO_PATH}/scripts/auto_deploy.sh"

CRON_LINE="${SCHEDULE} ${SCRIPT} >> ${LOG_FILE} 2>&1"

# Replace any existing auto-deploy entry, keep everything else.
existing="$(crontab -l 2>/dev/null | grep -v 'auto_deploy.sh' || true)"
printf '%s\n%s\n' "${existing}" "${CRON_LINE}" | sed '/^$/d' | crontab -

echo "Installed cron entry:"
echo "  ${CRON_LINE}"
