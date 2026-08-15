#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

load_environment
require_command tar

[[ "${PORTAL_DATA_DIR}" == /* && "${PORTAL_DATA_DIR}" != "/" ]] || fail "Unsafe PORTAL_DATA_DIR: ${PORTAL_DATA_DIR}"
[[ -d "${PORTAL_DATA_DIR}" ]] || fail "Portal data directory does not exist: ${PORTAL_DATA_DIR}"

backup_dir="${1:-${PROJECT_ROOT}/backups}"
mkdir -p "${backup_dir}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
archive="${backup_dir}/vllm-management-portal-${timestamp}.tar.gz"

as_root tar -C "$(dirname "${PORTAL_DATA_DIR}")" -czf "${archive}" "$(basename "${PORTAL_DATA_DIR}")"
as_root chown "${USER}:$(id -gn)" "${archive}"
log "Backup created: ${archive}"
