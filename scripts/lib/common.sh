#!/usr/bin/env bash

set -euo pipefail

COMMON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${COMMON_DIR}/../.." && pwd)"
COMPOSE_FILE="${PROJECT_ROOT}/compose.yaml"
ENV_FILE="${PROJECT_ROOT}/.env"

log() {
  printf '[vllm-portal] %s\n' "$*"
}

fail() {
  printf '[vllm-portal] ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" > /dev/null 2>&1 || fail "Required command not found: $1"
}

compose() {
  docker compose --project-directory "${PROJECT_ROOT}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" "$@"
}

load_environment() {
  [[ -f "${ENV_FILE}" ]] || fail "Missing ${ENV_FILE}; run scripts/deploy.sh first"
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
}

as_root() {
  if [[ "${EUID}" -eq 0 ]]; then
    "$@"
  else
    require_command sudo
    sudo "$@"
  fi
}
