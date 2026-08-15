#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

load_environment
require_command curl

attempts=1
if [[ "${1:-}" == "--wait" ]]; then
  attempts=30
elif [[ -n "${1:-}" ]]; then
  fail "Usage: scripts/healthcheck.sh [--wait]"
fi

url="http://127.0.0.1:${PORTAL_PORT}/api/v1/health"
for ((attempt = 1; attempt <= attempts; attempt++)); do
  if response="$(curl --fail --silent --show-error --max-time 10 "${url}" 2> /dev/null)"; then
    printf '%s\n' "${response}"
    exit 0
  fi
  if ((attempt < attempts)); then
    sleep 2
  fi
done

fail "Portal health endpoint did not become ready at ${url}"
