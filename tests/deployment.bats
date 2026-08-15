#!/usr/bin/env bats

setup() {
  PROJECT_ROOT="$(cd "${BATS_TEST_DIRNAME}/.." && pwd)"
  export PROJECT_ROOT
}

@test "all deployment images use exact tags" {
  run "${PROJECT_ROOT}/scripts/check-image-pins.sh"
  [ "${status}" -eq 0 ]
}

@test "compose enables boot restart for both services" {
  run docker compose \
    --project-directory "${PROJECT_ROOT}" \
    --env-file "${PROJECT_ROOT}/.env-template" \
    -f "${PROJECT_ROOT}/compose.yaml" \
    config --format json
  [ "${status}" -eq 0 ]

  run python3 -c '
import json, sys
config = json.load(sys.stdin)
assert config["services"]["portal"]["restart"] == "unless-stopped"
assert config["services"]["docker-socket-proxy"]["restart"] == "unless-stopped"
' <<< "${output}"
  [ "${status}" -eq 0 ]
}

@test "portal does not join or alter the existing vLLM compose project" {
  run grep -E 'containerized-vllm-amd-r9700|/var/lib/vllm/huggingface' "${PROJECT_ROOT}/compose.yaml"
  [ "${status}" -eq 1 ]
}

@test "shell deployment scripts parse successfully" {
  run bash -n \
    "${PROJECT_ROOT}/healthcheck.sh" \
    "${PROJECT_ROOT}"/scripts/*.sh \
    "${PROJECT_ROOT}/scripts/lib/common.sh"
  [ "${status}" -eq 0 ]
}

@test "shared library does not overwrite a caller script directory" {
  run bash -c '
SCRIPT_DIR=/caller/scripts
source "$1/scripts/lib/common.sh"
test "$SCRIPT_DIR" = /caller/scripts
' _ "${PROJECT_ROOT}"
  [ "${status}" -eq 0 ]
}

@test "AMD SMI wrapper uses the mounted ROCm runtime" {
  run grep -F 'export LD_LIBRARY_PATH=' "${PROJECT_ROOT}/container/amd-smi"
  [ "${status}" -eq 0 ]
  run grep -F 'libdrm-amdgpu1' "${PROJECT_ROOT}/Dockerfile"
  [ "${status}" -eq 0 ]
}
