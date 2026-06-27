#!/usr/bin/env bash
# Install the daily price-fetch cron job on the VPS host (idempotent).
# Run once per machine: bash scripts/install-cron.sh
set -euo pipefail

REPO_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKER_BIN="$(command -v docker)"
SCHEDULE="${PRICE_FETCH_SCHEDULE:-30 4 * * *}"
LOG_FILE="${PRICE_FETCH_LOG:-/var/log/price-fetch.log}"

CRON_CMD="cd ${REPO_PATH} && ${DOCKER_BIN} compose run --rm price-fetch >> ${LOG_FILE} 2>&1"
CRON_LINE="${SCHEDULE} ${CRON_CMD}"

# Replace any existing price-fetch entry, keep everything else.
existing="$(crontab -l 2>/dev/null | grep -v 'app.jobs.fetch_prices\|price-fetch' || true)"
printf '%s\n%s\n' "${existing}" "${CRON_LINE}" | sed '/^$/d' | crontab -

echo "Installed cron entry:"
echo "  ${CRON_LINE}"
