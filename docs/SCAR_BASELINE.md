# scar.lab Read-Only Baseline

Captured on 2026-08-14 through the portal's read-only discovery providers.
Telemetry is instantaneous and will vary with workload. No container, image,
driver, ROCm component, model, or deployment configuration was changed.

| Capability | Observed value | Source |
| --- | --- | --- |
| Host | `scar.lab` | Linux/socket discovery |
| OS | Ubuntu 24.04 | `/etc/os-release` |
| Kernel | `7.0.0-28-generic` | Linux platform API |
| Architecture | `x86_64` | Linux platform API |
| GPU | AMD Radeon AI PRO R9700 | AMD SMI static data |
| GPU VRAM | 31.86 GiB total | AMD SMI metric data |
| Telemetry provider | `amd-smi` | Provider selection |
| GPU utilization | 37% at final capture | AMD SMI metric data |
| VRAM used/free | 29.88 / 1.97 GiB at final capture | AMD SMI metric data |
| Temperature | 41 °C at final capture | AMD SMI edge sensor |
| Power | 46 W draw; 300 W configured limit | AMD SMI |
| ROCm | 7.2.2 | `amd-smi version` |
| Container runtime | Docker 29.7.2 | Docker server API/CLI |
| Lifecycle mechanism | Docker Compose | Container Compose labels |
| Compose project | `containerized-vllm-amd-r9700` | Container label |
| Compose file | `/home/cpaquin/Workspace/Gitrepos/Containerized-VLLM-AMD-R9700/compose.yaml` | Container label |
| Compose service | `vllm` | Container label |
| Container health | Healthy | Docker health state |
| Image | `rocm/vllm:rocm7.14.0_rdna_ubuntu24.04_py3.14_pytorch_2.11.0_vllm_0.23.0` | Docker inspect |
| Runtime vLLM version | `0.23.1.dev1+g9ddef7117.d20260715` | vLLM startup log |
| Active model | `stelterlab/Qwen3-Coder-30B-A3B-Instruct-AWQ` | `/v1/models` |
| Served model name | `qwen3-coder-30b-a3b` | `/v1/models` |
| Model cache | `/var/lib/vllm/huggingface` | Docker bind-mount mapping |
| Requested/effective max model length | 32,768 / 32,768 tokens | Container environment and vLLM API/log |
| Requested GPU memory utilization | 0.68 | Container environment |
| vLLM API | Healthy | `/health` and `/v1/models` |
| vLLM metrics | Healthy | `/metrics` |
| KV-cache utilization | 0% at final idle capture | Prometheus metric |
| KV-cache allocation | 4.61 GiB | vLLM startup log |
| KV-cache capacity | 50,336 tokens | vLLM startup log |
| Maximum concurrency | 1.54× at 32,768 tokens | vLLM startup log |
| Model-weight memory | 15.74 GiB | vLLM startup log |
| vLLM process VRAM | 22.69 GiB at final capture | AMD SMI process data matched to Docker host PID |
| External process VRAM | 0 GiB reported at final capture | AMD SMI process data excluding Docker host PID |
| Unattributed GPU memory | Approximately 7.19 GiB at final capture | Measured total minus process-attributed memory; not classified as external |
| Remaining VRAM headroom | 1.97 GiB at final capture | AMD SMI free VRAM |

## Unavailable values

- Runtime/activation VRAM is unavailable because this vLLM startup log does
  not report a separately attributable value.
- Backend/non-Torch VRAM is unavailable for the same reason.
- AMD SMI returned process names as `N/A`; the vLLM process was identified by
  matching its PID to Docker's inspected host PID.
- Approximately 7.19 GiB was not attributed by AMD SMI process accounting.
  It may include runtime, driver, display, or other allocations, so the portal
  does not silently classify it as external application memory.
- Native model context was not fetched from authoritative model metadata in
  this milestone; only requested and effective vLLM context are reported.
- Non-streaming basic benchmarking cannot reliably report TTFT, TPOT, or ITL.

## Lifecycle safety evidence

The adapter detected Docker Compose from existing container labels. It is in
monitoring/preview-only mode. The proposed actions are:

```text
docker compose -f /home/cpaquin/Workspace/Gitrepos/Containerized-VLLM-AMD-R9700/compose.yaml up -d vllm
docker compose -f /home/cpaquin/Workspace/Gitrepos/Containerized-VLLM-AMD-R9700/compose.yaml stop vllm
docker compose -f /home/cpaquin/Workspace/Gitrepos/Containerized-VLLM-AMD-R9700/compose.yaml restart vllm
docker compose -f /home/cpaquin/Workspace/Gitrepos/Containerized-VLLM-AMD-R9700/compose.yaml ps --format json vllm
```

No lifecycle command was executed. Known-good records can be created only
from snapshots showing a healthy Docker container, API, and metrics endpoint.
Actual restore remains disabled until configuration preservation, validated
rendering, atomic replacement, post-start health monitoring, and rollback are
implemented and tested.

## Basic live benchmark validation

One deterministic, non-streaming request was executed and persisted in an
isolated in-memory SQLite database:

```text
Prompt: Return only the word READY.
Prompt tokens: 6
Output tokens: 8
Concurrency: 1
Seed: 1
End-to-end latency: 2.969 seconds
Output throughput: 2.694 tokens/second
```

This validates the basic execution/persistence path, not the complete
benchmarking requirements. The response reached the requested eight-token
limit, and the test is not yet a representative interactive benchmark.
