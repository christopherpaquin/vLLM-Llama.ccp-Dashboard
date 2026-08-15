#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for command in docker awk; do
  command -v "${command}" > /dev/null 2>&1 || {
    echo "Required command not found: ${command}" >&2
    exit 3
  }
done

images="$(docker compose --project-directory "${ROOT}" --env-file "${ROOT}/.env-template" -f "${ROOT}/compose.yaml" config --images)"
images+=$'\n'
images+="$(awk -F= '/^ARG [A-Z0-9_]*IMAGE=/{print $2}' "${ROOT}/Dockerfile")"

failed=false
while IFS= read -r image; do
  [[ -n "${image}" ]] || continue
  tag="${image##*:}"
  if [[ "${image}" != *:* || "${tag}" =~ ^(latest|main|master|stable|dev|edge|nightly|rolling)$ ]]; then
    echo "Floating or missing image tag: ${image}" >&2
    failed=true
  fi
done <<< "${images}"

[[ "${failed}" == false ]]
