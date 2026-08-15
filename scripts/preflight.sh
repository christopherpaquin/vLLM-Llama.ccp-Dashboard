#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091 # Path is resolved from this script at runtime.
source "${SCRIPT_DIR}/lib/common.sh"

require_command docker
require_command curl
docker info > /dev/null 2>&1 || fail "Docker daemon is not accessible to ${USER}"
docker compose version > /dev/null 2>&1 || fail "Docker Compose plugin is unavailable"

[[ -f "${PROJECT_ROOT}/Dockerfile" ]] || fail "Dockerfile is missing"
[[ -f "${COMPOSE_FILE}" ]] || fail "compose.yaml is missing"

if [[ ! -f "${ENV_FILE}" ]]; then
  log "No .env found; deploy will create it from .env-template"
  exit 0
fi

load_environment
[[ -n "${HOST_ROUTE_PROBE_IP:-}" ]] || fail "HOST_ROUTE_PROBE_IP must not be empty"
[[ "${PORTAL_DATA_DIR:-}" == /* ]] || fail "PORTAL_DATA_DIR must be an absolute path"
[[ "${PORTAL_DATA_DIR}" != "/" ]] || fail "PORTAL_DATA_DIR cannot be /"
[[ -d "${ROCM_PATH:-/nonexistent}" ]] || fail "Configured ROCm path does not exist: ${ROCM_PATH:-unset}"
[[ -f "${AMDGPU_IDS_PATH:-/nonexistent}" ]] || fail "Configured AMD GPU ID table does not exist: ${AMDGPU_IDS_PATH:-unset}"
[[ -e /dev/kfd && -d /dev/dri ]] || fail "AMD GPU device nodes /dev/kfd and /dev/dri are required"

log "Preflight passed"
