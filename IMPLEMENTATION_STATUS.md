# Infrence Engine Dashboard — Implementation Status

Last verified: 2026-08-15

Statuses describe working, tested behavior. Interfaces, database columns, and
stubs are not counted as complete.

| Feature | Status | Evidence / remaining work |
| --- | --- | --- |
| FastAPI application shell | Partial | Application and routes run in the pinned production container; schema migrations remain absent. |
| SQLite persistence | Partial | Deployment persists SQLite under `/var/lib/vllm-management-portal`; migrations and broader relationship constraints remain missing. |
| Host discovery | Complete for scar baseline | Tested read-only discovery reports hostname, primary IP, OS, kernel, architecture, uptime, CPU model/counts, memory, root storage, SELinux, and AppArmor. Additional filesystem detail and multi-distribution live validation remain. |
| AMD telemetry | Complete for scar baseline | AMD SMI is preferred with tested ROCm SMI fallback. Normalized bytes, utilization, temperature, power, clocks, identity, ROCm, and process VRAM work live on scar. The host AMD ID table preserves the exact R9700 model name in-container. |
| NVIDIA telemetry | Partial | A narrow `nvidia-smi` CSV parser exists. NVML preference, identity, temperature, power, clocks, processes, robust unavailable values, and tests are missing. |
| Multi-GPU handling | Partial | Data structures are collections and the NVIDIA parser can return multiple rows, but no tested discovery/dashboard integration exists. |
| Runtime discovery | Partial | Docker and Docker Compose discovery is tested and live-validated on scar, including positive inference-container selection that excludes the dashboard and proxy. Other target runtimes remain missing; scar correctly reports no Podman. |
| Inference connectivity and metrics | Partial | vLLM health/model/metrics/KV discovery is tested and live-validated. llama.cpp health, model, properties, optional metrics, and throughput normalization are tested against its official API contract and live-validated on scar. |
| Lifecycle management | Safe preview only | Exact Docker Compose actions are derived from existing labels. The adapter validates file/service inputs and raises `LifecycleDisabled` for every mutation until preservation and restore gates exist. |
| Model records | Partial | Active models/profiles can be synchronized. Bounded read-only discovery supports Hugging Face snapshots for vLLM and GGUF files for llama.cpp. Metadata/downloads and removal safeguards remain missing. |
| Compatibility assessment | Stub | Endpoint echoes/defaults fields and does not perform the required advisory assessment. |
| Runtime profiles | Partial | Basic records and typed create/update validation exist, including bounds and model referential checks. Advanced/multi-GPU fields, requested-vs-observed state, preflight integration, and broader tests are missing. |
| VRAM preflight | Stub | Inputs now require explicit non-negative memory values, positive capacity, and a valid utilization fraction, with arithmetic unit coverage. The assessment/recommendation logic remains incomplete and is not a reliable fit guarantee. |
| Safe switching / last-known-good | Partial | Health-gated known-good snapshot records exist and are tested. Restore and switching remain deliberately disabled pending atomic configuration preservation/recovery. |
| Detailed VRAM and KV accounting | Partial | Live-tested vLLM log/metric parsing reports weights, KV allocation/capacity/utilization, process VRAM, unattributed VRAM, and headroom with sources. Activation/backend breakdown remains unavailable. |
| Client context awareness | Missing | No detection is implemented. |
| Benchmark execution | Partial | Bounded deterministic basic and interactive-streaming benchmarks execute and persist. Live scar validation measured TTFT, output tokens/sec, and E2E latency. Coding/long-context/concurrency/prefix presets, percentiles, warmups, resource sampling, and full metadata remain missing. |
| Benchmark history/comparison | Partial | Flat records can be listed. Filtering, tags/notes, normalized environment metadata, comparison, and frontend are missing. |
| Operation history and logs | Partial | A generic log table and unvalidated endpoints exist. Lifecycle event capture, bounded/tailable manager and vLLM logs, and access scoping are missing. |
| Health reporting | Partial | Manager response, database, vLLM API, metrics, and GPU telemetry checks are implemented and live-tested. Adapter failure detail can be expanded. |
| Authentication and authorization | Missing | No authentication, sessions, password hashing, logout, or rate limiting exists. |
| Frontend | Partial | The Infrence Engine Dashboard is deployed on scar with host identity/hardware, active model/health, VRAM/GPU/KV summaries, provider-specific runtime details, explicit dropdown states, cached models, and interactive benchmark results. Model activation remains safety-locked; history and advanced workflows are absent. |
| Containerized deployment | Complete for scar baseline | One-click Docker Compose deployment uses pinned images, a non-root/read-only portal, least-privilege Docker socket proxy, persistent data, healthcheck, and `unless-stopped` boot restart. Live deployed on scar. |
| Backup / uninstall | Complete for scar baseline | Tested scripts back up persistent data and uninstall containers while preserving data by default. Purge is restricted to the exact portal data path and never touches vLLM. |
| Automated tests | Partial | 33 pytest and 11 BATS tests cover backend/dashboard behavior, provider-specific details, vLLM/llama.cpp parsing/configuration, inference-container selection, image pinning, container identity, restart policy, environment-driven host identity, portability, read-only cache/AMD identity mounting, AMD SMI, and shell safety. Broader browser/matrix/security coverage remains. |
| CI and pre-commit | Partial | Local pre-commit syntax, secret detection, and exact image-pin gates exist; hosted CI remains missing. |
| Documentation | Partial | README documents deployment, development, health, backup, and uninstall. Dedicated architecture, security, and benchmark guides remain missing. |
| Live validation on reference host | Partial | Portal is running healthy on port 8088 with AMD SMI, Docker/llama.cpp discovery, durable storage, and boot restart. The existing healthy llama.cpp container remained unchanged; no lifecycle command was executed. |

## Current milestone

Establish a trustworthy safety baseline before enabling any host-changing
operation:

1. ~~add typed model/profile/memory API input validation and tests~~;
2. ~~implement tested read-only scar host, AMD GPU, Docker Compose, vLLM API/metrics, and startup telemetry discovery~~;
3. ~~persist observed model/profile state, requested-vs-observed snapshots, and health-gated known-good records~~;
4. ~~execute and persist one bounded basic endpoint benchmark~~;
5. ~~add one-click, boot-persistent, isolated Docker deployment for the management API~~;
6. implement configuration preservation, validated rendering, atomic restore, and mocked failure recovery before enabling lifecycle actions;
7. add representative streaming benchmark presets and resource sampling.

## Known repository risks

- Lifecycle mutations are intentionally disabled; do not bypass the adapter's
  preservation and recovery gates on a production vLLM host.
