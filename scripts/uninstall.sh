#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

purge_data=false
case "${1:-}" in
  "") ;;
  --purge-data) purge_data=true ;;
  *) fail "Usage: scripts/uninstall.sh [--purge-data]" ;;
esac

load_environment
compose down --remove-orphans
log "Removed management-portal containers and network; portal data was preserved"

if [[ "${purge_data}" == true ]]; then
  [[ "${PORTAL_DATA_DIR}" == /* && "${PORTAL_DATA_DIR}" != "/" ]] || fail "Unsafe PORTAL_DATA_DIR: ${PORTAL_DATA_DIR}"
  [[ "${PORTAL_DATA_DIR}" == "/var/lib/vllm-management-portal" ]] || fail "Refusing to purge unexpected path: ${PORTAL_DATA_DIR}"
  as_root rm -rf -- "${PORTAL_DATA_DIR}"
  log "Permanently removed portal data: ${PORTAL_DATA_DIR}"
fi

log "The existing vLLM deployment, images, and model cache were not changed"
