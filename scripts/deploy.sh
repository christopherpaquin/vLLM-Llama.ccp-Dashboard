#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

if [[ ! -f "${ENV_FILE}" ]]; then
  cp "${PROJECT_ROOT}/.env-template" "${ENV_FILE}"
  log "Created ${ENV_FILE} from .env-template"
fi

"${SCRIPT_DIR}/preflight.sh"

load_environment
[[ "${PORTAL_DATA_DIR}" == /* && "${PORTAL_DATA_DIR}" != "/" ]] || fail "Unsafe PORTAL_DATA_DIR: ${PORTAL_DATA_DIR}"

as_root install -d -m 0750 -o 10001 -g 10001 "${PORTAL_DATA_DIR}"

log "Building the pinned management portal image"
compose build --pull portal

log "Starting the portal with boot-time restart policy ${RESTART_POLICY}"
compose up -d --remove-orphans

"${SCRIPT_DIR}/healthcheck.sh" --wait
log "Deployment complete: http://${PORTAL_BIND_ADDRESS}:${PORTAL_PORT}"
