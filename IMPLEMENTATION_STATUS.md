# vLLM Management Portal — Implementation Status

Last verified: 2026-08-14

Statuses describe working, tested behavior. Interfaces, database columns, and
stubs are not counted as complete.

| Feature | Status | Evidence / remaining work |
| --- | --- | --- |
| FastAPI application shell | Partial | Application and routes exist, but startup creates tables implicitly and production configuration is absent. |
| SQLite persistence | Partial | SQLAlchemy models and CRUD calls exist; migrations, durable deployment storage, relationship constraints, and persistence tests are missing. |
| Host discovery | Complete for scar baseline | Tested read-only discovery reports OS, hostname, kernel, architecture, uptime, CPU, memory, root storage, SELinux, and AppArmor. Additional filesystem detail and multi-distribution live validation remain. |
| AMD telemetry | Complete for scar baseline | AMD SMI is preferred with tested ROCm SMI fallback. Normalized bytes, utilization, temperature, power, clocks, identity, ROCm, and process VRAM work live on scar. |
| NVIDIA telemetry | Partial | A narrow `nvidia-smi` CSV parser exists. NVML preference, identity, temperature, power, clocks, processes, robust unavailable values, and tests are missing. |
| Multi-GPU handling | Partial | Data structures are collections and the NVIDIA parser can return multiple rows, but no tested discovery/dashboard integration exists. |
| Runtime discovery | Partial | Docker and Docker Compose discovery is tested and live-validated on scar. Other target runtimes remain missing; scar correctly reports no Podman. |
| vLLM connectivity and metrics | Partial | Health, model listing, and Prometheus reachability plus KV utilization are tested/live-validated. Broader metric normalization remains. |
| Lifecycle management | Safe preview only | Exact Docker Compose actions are derived from existing labels. The adapter validates file/service inputs and raises `LifecycleDisabled` for every mutation until preservation and restore gates exist. |
| Model records | Partial | Active model and an observed profile can be synchronized from reliable runtime evidence. Local cache enumeration, metadata/downloads, and removal safeguards remain missing. |
| Compatibility assessment | Stub | Endpoint echoes/defaults fields and does not perform the required advisory assessment. |
| Runtime profiles | Partial | Basic records and typed create/update validation exist, including bounds and model referential checks. Advanced/multi-GPU fields, requested-vs-observed state, preflight integration, and broader tests are missing. |
| VRAM preflight | Stub | Inputs now require explicit non-negative memory values, positive capacity, and a valid utilization fraction, with arithmetic unit coverage. The assessment/recommendation logic remains incomplete and is not a reliable fit guarantee. |
| Safe switching / last-known-good | Partial | Health-gated known-good snapshot records exist and are tested. Restore and switching remain deliberately disabled pending atomic configuration preservation/recovery. |
| Detailed VRAM and KV accounting | Partial | Live-tested vLLM log/metric parsing reports weights, KV allocation/capacity/utilization, process VRAM, unattributed VRAM, and headroom with sources. Activation/backend breakdown remains unavailable. |
| Client context awareness | Missing | No detection is implemented. |
| Benchmark execution | Partial | A bounded deterministic non-streaming endpoint benchmark executes and persists, with a live scar smoke run. Required benchmark types, streaming latency metrics, warmups, sampling, and full metadata remain missing. |
| Benchmark history/comparison | Partial | Flat records can be listed. Filtering, tags/notes, normalized environment metadata, comparison, and frontend are missing. |
| Operation history and logs | Partial | A generic log table and unvalidated endpoints exist. Lifecycle event capture, bounded/tailable manager and vLLM logs, and access scoping are missing. |
| Health reporting | Partial | Manager response, database, vLLM API, metrics, and GPU telemetry checks are implemented and live-tested. Adapter failure detail can be expanded. |
| Authentication and authorization | Missing | No authentication, sessions, password hashing, logout, or rate limiting exists. |
| Frontend | Missing | No frontend source exists in the repository. |
| Containerized deployment | Missing | No image definition, persistent mount configuration, or deployment scripts exist. |
| Backup / uninstall | Missing | Required safe operational scripts do not exist. |
| Automated tests | Partial | 19 tests cover validation, API integration, Linux discovery, AMD SMI/ROCm SMI normalization, Docker Compose detection/action preview, lifecycle mutation blocking, metrics/log parsing, runtime persistence, and basic benchmarking. Broader matrix/security coverage remains. |
| CI and pre-commit | Missing | No repository quality/security gates exist. |
| Documentation | Partial | `GOALS.md` is comprehensive. README currently claims unavailable behavior and references missing Alembic/frontend components. Architecture, security, benchmarking, development, deployment, backup, and uninstall docs are missing. |
| Live validation on `scar.lab` | Partial | Read-only host/GPU/Docker/vLLM telemetry, persistence flows, known-good gating, and one bounded benchmark were validated. See `docs/SCAR_BASELINE.md`. No lifecycle command was executed. |

## Current milestone

Establish a trustworthy safety baseline before enabling any host-changing
operation:

1. ~~add typed model/profile/memory API input validation and tests~~;
2. ~~implement tested read-only scar host, AMD GPU, Docker Compose, vLLM API/metrics, and startup telemetry discovery~~;
3. ~~persist observed model/profile state, requested-vs-observed snapshots, and health-gated known-good records~~;
4. ~~execute and persist one bounded basic endpoint benchmark~~;
5. implement configuration preservation, validated rendering, atomic restore, and mocked failure recovery before enabling lifecycle actions;
6. add representative streaming benchmark presets and resource sampling.

## Known repository risks

- The staged tree includes `venv/` and Python bytecode/cache files. These
  should be removed from version control after confirming the staged import
  is not intentionally being preserved.
- The staged virtual environment is not a supported distribution artifact;
  dependencies should be recreated from `backend/requirements.txt`.
- Lifecycle mutations are intentionally disabled; do not bypass the adapter's
  preservation and recovery gates on a production vLLM host.
