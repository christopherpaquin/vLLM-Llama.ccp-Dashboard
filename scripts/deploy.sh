#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/common.sh disable=SC1091
source "${SCRIPT_DIR}/lib/common.sh"

if [[ ! -f "${ENV_FILE}" ]]; then
  cp "${PROJECT_ROOT}/.env-template" "${ENV_FILE}"
  log "Created ${ENV_FILE} from .env-template"
fi

"${SCRIPT_DIR}/preflight.sh"

load_environment
[[ "${PORTAL_DATA_DIR}" == /* && "${PORTAL_DATA_DIR}" != "/" ]] || fail "Unsafe PORTAL_DATA_DIR: ${PORTAL_DATA_DIR}"

require_command awk
require_command ip
HOST_PRIMARY_IP="$(ip -4 route get 1.1.1.1 | awk '{for (i=1; i<=NF; i++) if ($i == "src") {print $(i+1); exit}}')"
[[ -n "${HOST_PRIMARY_IP}" ]] || HOST_PRIMARY_IP="Unknown"
export HOST_PRIMARY_IP

as_root install -d -m 0750 -o 10001 -g 10001 "${PORTAL_DATA_DIR}"

log "Building the pinned vLLM Dashboard image"
compose build --pull portal

log "Starting the portal with boot-time restart policy ${RESTART_POLICY}"
compose up -d --remove-orphans

"${SCRIPT_DIR}/healthcheck.sh" --wait
log "Deployment complete: http://${PORTAL_BIND_ADDRESS}:${PORTAL_PORT}"
