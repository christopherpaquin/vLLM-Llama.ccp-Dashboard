# vLLM Management Portal — Product Goals and Requirements

## 1. Purpose

The vLLM Management Portal is a portable, containerized web application for **managing, observing, tuning, and benchmarking existing vLLM deployments**.

The portal is intended to make local vLLM operation substantially easier by providing a well-designed management interface for:

* system and GPU monitoring
* model discovery and management
* model switching
* reusable vLLM runtime profiles
* context-window tuning
* GPU/VRAM tuning
* KV-cache visibility
* controlled vLLM lifecycle operations
* reproducible performance benchmarking
* tuning experiments
* benchmark history
* model/profile/hardware comparisons
* troubleshooting and operational visibility

This application is **not a chat frontend**.

The application should feel more like an infrastructure appliance or virtualization-management interface than an LLM chat application.

The primary workflow is:

```text
Discover model
      ↓
Download model
      ↓
Inspect compatibility
      ↓
Create runtime profile
      ↓
Estimate resource requirements
      ↓
Activate safely
      ↓
Observe actual runtime allocation
      ↓
Benchmark
      ↓
Tune
      ↓
Benchmark again
      ↓
Compare
      ↓
Save known-good configuration
```

---

# 2. Durable Project Instructions

This file is the authoritative product specification for this repository.

Before performing substantive development work:

1. Read `GOALS.md`.
2. Read `IMPLEMENTATION_STATUS.md` if it exists.
3. Read `ARCHITECTURE.md` or relevant architecture documentation before architectural changes.
4. Inspect the actual implementation rather than assuming features exist because they are documented.
5. Treat `GOALS.md` as authoritative when conversational context is incomplete or has been compacted.
6. Do not remove, weaken, or reinterpret requirements without explicit user direction.
7. After LLM/OpenCode context compaction, reread this file before continuing development.
8. Update implementation-status documentation whenever feature status materially changes.
9. Update `GOALS.md` only when product requirements actually change.
10. Keep implementation details out of this document unless they are architectural requirements.

This document should remain a **product specification**, not a development journal.

---

# 3. Core Architectural Principle

The portal is a **vLLM management application**.

The following are discoverable implementation capabilities, not assumptions built into the application:

* Linux distribution
* Linux version
* GPU vendor
* GPU model
* GPU count
* GPU telemetry provider
* CUDA or ROCm runtime
* container runtime
* vLLM lifecycle mechanism
* model-cache location
* vLLM version
* vLLM deployment topology

The architecture should use adapters/providers so platform-specific logic remains isolated.

Conceptually:

```text
                       vLLM Manager
                            |
        +-------------------+-------------------+
        |                   |                   |
        v                   v                   v
 System Provider       GPU Provider       Runtime Provider
        |                   |                   |
 Ubuntu/Fedora         AMD / NVIDIA     Docker / Podman /
 RHEL/etc.              telemetry        systemd / Quadlet
        |
        +-------------------+-------------------+
                            |
                            v
                     Existing vLLM
```

The frontend and core business logic should operate on normalized APIs and data structures rather than vendor-specific command output.

---

# 4. Existing vLLM Deployment Must Remain Independent

The portal runs **alongside** an existing vLLM deployment.

The existing vLLM deployment remains the source of truth for its underlying runtime.

The portal must not automatically:

* replace the vLLM container image
* upgrade vLLM
* upgrade ROCm
* upgrade CUDA
* modify GPU drivers
* rebuild a known-working vLLM deployment
* change unrelated host configuration
* change container security settings without justification
* delete local models
* take ownership of unrelated containers or services

If the portal is stopped, broken, upgraded, or completely removed:

> The existing vLLM deployment must remain independently usable.

---

# 5. Target Platforms

The architecture must support or be designed cleanly to support the following.

## Linux

Initial target distributions:

* Ubuntu 24.04
* Ubuntu 26.04
* Fedora
* Red Hat Enterprise Linux

The design should not artificially prevent support for other modern Linux distributions.

## GPU Vendors

At minimum:

* AMD GPUs using ROCm
* NVIDIA GPUs using CUDA

## GPU Topology

Support:

* single GPU
* multiple GPUs
* future tensor-parallel vLLM configurations
* future pipeline-parallel configurations where applicable

Never globally assume:

```text
gpu = GPU0
```

Use collections such as:

```text
gpus[]
```

---

# 6. Deployment and Lifecycle Types

The manager should support or have adapters for:

* Docker
* Docker Compose
* Podman
* Podman Compose
* Podman Quadlet
* systemd-managed vLLM
* externally managed vLLM

At least two management modes are required.

## Managed Mode

The portal can safely:

* start vLLM
* stop vLLM
* restart vLLM
* apply an approved runtime profile
* switch models
* inspect logs
* run health checks

## External / Monitoring Mode

When lifecycle control is unavailable or intentionally disabled, the portal can still:

* connect to the vLLM API
* read vLLM metrics
* monitor the GPU
* run endpoint benchmarks
* display configuration information where discoverable

The portal should gracefully show:

```text
Lifecycle control: Monitoring only
```

rather than failing.

---

# 7. Host Integration and Security Boundary

The web application must not require unrestricted host control.

Avoid giving the primary web process:

* unrestricted Docker socket access
* unrestricted Podman socket access
* arbitrary host shell execution
* broad root filesystem access
* unnecessary root privileges

Where host-level lifecycle or telemetry access is required, prefer a constrained host integration layer or agent.

Example conceptual operations:

```text
GET  /system
GET  /gpus
GET  /runtime
GET  /vllm
GET  /storage

POST /vllm/start
POST /vllm/stop
POST /vllm/restart
POST /vllm/apply-profile
```

Do not expose endpoints equivalent to:

```text
POST /shell
POST /exec
POST /run-command
```

All lifecycle operations must use validated, predefined actions.

---

# 8. Host Capability Discovery

On startup and through an explicit refresh operation, discover the host non-destructively.

Capture:

## System

* hostname
* Linux distribution
* OS version
* kernel
* architecture
* uptime
* CPU information
* system memory
* filesystem/storage information

## Security Framework

Where applicable:

* SELinux status
* AppArmor status

## GPU

* GPU vendor
* GPU model
* number of GPUs
* VRAM per GPU
* driver version
* available telemetry mechanisms

## Compute Runtime

Where applicable:

* ROCm version
* CUDA version

## Container / Service Runtime

Detect:

* Docker
* Docker Compose
* Podman
* Podman Compose
* Quadlet
* systemd lifecycle
* external management

## vLLM

Detect where practical:

* API URL
* metrics URL
* current running state
* vLLM version
* active model
* container image
* lifecycle mechanism
* current configuration
* model/cache storage
* health endpoint availability

Discovery must be:

* idempotent
* non-destructive
* safe to rerun

---

# 9. GPU Telemetry Architecture

Use a normalized internal GPU telemetry model.

Common fields should include where available:

```text
device_index
uuid

vendor
model

vram_total
vram_used
vram_free

gpu_utilization
memory_utilization

temperature

power_draw
power_limit

core_clock
memory_clock

driver_version
compute_runtime_version

processes[]
```

Missing metrics must be represented as unavailable rather than invented.

---

# 10. AMD GPU Monitoring

For AMD GPUs, prefer modern structured telemetry.

Preferred hierarchy:

```text
AMD GPU
   ↓
AMD SMI available?
   ↓
AMD SMI provider
   ↓ fallback
ROCm SMI
   ↓ fallback
limited kernel/sysfs telemetry
```

Do not hard-code support specifically for the Radeon AI Pro R9700.

The implementation should work with other supported AMD GPUs where practical.

Vendor command output must be parsed inside the provider layer and converted to normalized application data.

---

# 11. NVIDIA GPU Monitoring

For NVIDIA GPUs, prefer:

```text
NVML
   ↓ fallback
nvidia-smi
```

GPUtil must **not** become the primary cross-platform telemetry abstraction.

GPUtil may be used only as a supplemental NVIDIA implementation if it adds value and remains isolated behind the provider architecture.

The common frontend should not require separate AMD and NVIDIA implementations for basic resource monitoring.

---

# 12. Multi-GPU Dashboard

The dashboard must support multiple GPUs.

Example concept:

```text
GPU 0
NVIDIA T4
14.8 / 16 GiB
Utilization: 91%

GPU 1
NVIDIA T4
15.1 / 16 GiB
Utilization: 94%

GPU 2
NVIDIA T4
0.8 / 16 GiB
Utilization: 3%
```

Where possible, identify which GPUs are assigned to the active vLLM instance.

Future profile fields should be capable of representing:

* selected devices
* tensor parallel size
* pipeline parallel size

---

# 13. Main Dashboard

The primary dashboard should provide an immediate operational view.

## Host

Show:

* hostname
* OS
* kernel
* uptime
* CPU utilization
* system RAM utilization

## GPU

For every GPU show:

* vendor/model
* utilization
* VRAM used/total
* temperature
* power where available
* driver/runtime
* telemetry provider

## vLLM

Show:

* running/stopped
* healthy/unhealthy
* API reachable
* metrics reachable
* active model
* active profile
* vLLM version
* container image
* configured context
* GPU memory utilization
* uptime

## KV Cache

Show where available:

* allocated KV-cache memory
* KV-cache token capacity
* current KV-cache utilization
* maximum concurrency
* prefix-cache hit rate

The dashboard should be concise and appliance-like.

---

# 14. Detailed VRAM Accounting

Detailed GPU memory accounting is a core feature.

The portal should distinguish:

```text
Model Weight Memory
KV Cache Memory
Runtime / Activation Memory
Backend / Non-Torch Memory
Other GPU Usage
VRAM Headroom
```

Do **not** treat context window itself as another independent VRAM category.

A desired presentation is:

```text
GPU MEMORY

Total VRAM                      31.4 GiB

vLLM
  Model weights                 18.7 GiB
  KV cache                       6.5 GiB
  Runtime / activations          1.5 GiB
  Backend / non-Torch            0.6 GiB

Other GPU processes              1.3 GiB

Free / headroom                  2.8 GiB
```

Numbers above are examples only.

Never invent memory values.

---

# 15. Memory Value Accuracy

Prefer actual measurements over estimates.

Every memory value should internally have a source classification such as:

```text
Measured
Reported by vLLM
Calculated
Estimated
Unavailable
```

Never present an estimate as an exact measured value.

Where vLLM provides startup memory profiling, capture information such as:

* model weight memory
* peak activation memory
* non-Torch/backend memory
* KV-cache memory
* total vLLM memory budget

Prefer structured APIs when available.

If startup-log parsing is required:

* isolate it behind a version-aware parser
* preserve raw logs
* fail gracefully when formats change
* report unavailable rather than fabricate values

---

# 16. External GPU Usage

This application may run on workstations that simultaneously use the GPU for:

* display output
* desktop compositor
* browser
* IDE
* OpenCode
* other applications

Where telemetry supports it, display GPU processes and their VRAM consumption.

Example:

```text
GPU PROCESSES

vLLM                  26.8 GiB
Desktop/compositor      0.6 GiB
Browser                 0.5 GiB
Other                   0.2 GiB
```

This is observational only.

Do not implement GPU process termination in v1.

---

# 17. Context Window Management

Context length must be a first-class tuning parameter.

Always distinguish:

```text
Model Native / Reported Context
vLLM Configured Context
Client Context Limit
Actual Request Context
KV Cache Capacity
KV Cache Utilization
```

Do not label all of these simply as:

```text
Context
```

---

# 18. Context Is Not Another VRAM Bucket

A configured context window is a token-count capability/configuration.

It affects how much KV cache individual sequences may require, but context memory must not be double-counted.

Wrong:

```text
Weights      18 GiB
KV Cache      7 GiB
Context       7 GiB
Runtime       2 GiB
```

Correct:

```text
VRAM

Weights      18 GiB
KV Cache      7 GiB
Runtime       2 GiB
Other         1 GiB
Free          4 GiB

Context

Configured   32K tokens
KV capacity  116K tokens
KV used       38%
```

---

# 19. Native Model Context

Determine native/reported model context from reliable model configuration or metadata.

Do not infer context capability from model parameter count.

If reliable metadata cannot be obtained:

```text
Native context: Unknown
```

Do not guess.

---

# 20. Configured vLLM Context

Expose the installed-version equivalent of:

```text
--max-model-len
```

as a prominent profile setting.

Potential presets:

```text
8K
16K
32K
64K
128K
Auto / Maximum that fits
```

Only display options appropriate to the selected model and installed vLLM version.

The application must distinguish:

* requested context
* effective context after startup

---

# 21. Client Context Awareness

Where practical, non-destructively detect client-side context limits.

OpenCode is an important initial client.

Display conceptually:

```text
Model native context       262K
vLLM configured context     64K
OpenCode configured context 32K
```

The portal does not need to modify OpenCode configuration initially.

Visibility is sufficient.

If detection is unavailable:

```text
Client context: Not detected
```

---

# 22. KV Cache Visibility

Where supported, show:

```text
KV cache memory allocated
KV cache capacity in tokens
KV cache utilization %
Maximum concurrency
Prefix-cache statistics
```

Do not confuse:

```text
max_model_len
```

with:

```text
total KV-cache token capacity
```

A running instance may conceptually have:

```text
Maximum sequence length   32K
KV cache capacity        116K
```

allowing several sequences to share the cache.

---

# 23. Model Management

The Models page should provide simplified management of local models.

Support:

* installed models
* active model
* available/downloadable models
* model download
* download progress
* failed-download state
* local storage usage
* model metadata
* last successful profile
* last benchmark

For each model, display reliable metadata where available:

```text
Friendly name
Hugging Face repository ID
Architecture
Parameter count
Active parameter count for MoE
Quantization
dtype
Disk size
Loaded weight VRAM
Native context
Installation state
Last used
Last benchmark
```

---

# 24. Model Compatibility Assessment

The portal should help users assess whether a model is likely to work.

Possible states:

```text
Compatible
Likely compatible
Low VRAM headroom
Likely too large
Unsupported
Unknown
```

Do not claim compatibility merely because a model exists on Hugging Face.

Compatibility assessment may consider:

* architecture support
* vLLM support
* model weight size
* dtype/quantization
* available VRAM
* current workstation VRAM usage
* context request
* KV requirements
* runtime overhead

Predictions are advisory, not guarantees.

---

# 25. Model Downloads

Allow supported Hugging Face models to be downloaded into the model/cache location already used by vLLM.

Requirements:

* do not duplicate models unnecessarily
* use persistent host storage
* show progress
* show failure state
* preserve partial-download safety where possible
* do not automatically delete models

Model deletion may be implemented later as an explicit, protected operation.

---

# 26. Model Storage Visibility

Show:

```text
Model/cache path
Filesystem total size
Used space
Free space
Number of installed models
Approximate model disk usage
```

Storage awareness is important because local LLM repositories can consume significant disk capacity.

---

# 27. Runtime Profiles

A runtime profile associates a model with its vLLM configuration.

Profiles must be persistent and named.

Example:

```text
Qwen3-Coder-30B / Workstation

Context                  32K
GPU memory utilization   82%
Prefix cache             Enabled
Max sequences            4
```

Another profile:

```text
Qwen3-Coder-30B / Maximum Context

Context                  64K
GPU memory utilization   92%
Prefix cache             Enabled
```

---

# 28. Profile Parameters

Where supported by the installed vLLM version, profiles may include:

```text
Model ID
Model revision
dtype
Quantization

max_model_len
gpu_memory_utilization
max_num_seqs
max_num_batched_tokens

prefix caching
KV cache dtype
explicit KV cache memory setting

CPU offload
swap space

GPU device assignment
tensor parallel size
pipeline parallel size
```

Do not expose every obscure vLLM CLI option by default.

Use a clean primary interface and an advanced section where appropriate.

---

# 29. Requested vs Observed Configuration

This distinction is critical.

Persist:

```text
REQUESTED PROFILE
```

separately from:

```text
OBSERVED RUNTIME RESULT
```

Observed startup state may include:

```text
effective max context
model weight VRAM
KV-cache VRAM
KV-cache token capacity
runtime/activation VRAM
backend/non-Torch VRAM
total vLLM VRAM
maximum concurrency
remaining VRAM
actual devices used
```

Do not assume requested values equal final runtime values.

---

# 30. Preflight Validation

Before applying a model/profile, perform a non-destructive preflight.

Consider:

* model architecture
* model size
* dtype
* quantization
* available VRAM
* current external GPU usage
* requested GPU-memory utilization
* requested context
* expected KV-cache requirements
* expected runtime overhead
* selected GPU count
* tensor-parallel configuration where applicable

Return a state such as:

```text
Expected to fit
Likely to fit
Low headroom
High OOM risk
Unknown
```

Warnings may be overridden when technically valid.

Do not claim estimated requirements are guaranteed.

---

# 31. Safe Model and Profile Switching

The switching workflow must preserve recoverability.

```text
Validate requested configuration
          ↓
Preserve current known-good profile
          ↓
Stop existing vLLM
          ↓
Apply approved configuration
          ↓
Start existing vLLM deployment
          ↓
Monitor startup
          ↓
Health check
          ↓
Capture observed runtime state
          ↓
Success
```

On failure:

```text
Display failure
Display relevant logs
Identify OOM if reliably detectable
Preserve failed configuration for analysis
Offer Restore Last Known Good
```

A failed configuration must never automatically replace the last-known-good profile.

---

# 32. Last-Known-Good Configuration

The manager should track:

```text
Desired configuration
Current configuration
Last-known-good configuration
```

A profile can become known-good after successful startup and health validation.

Benchmark success may additionally qualify the configuration as tested.

The UI should provide a clear:

```text
Restore Last Known Good
```

operation.

---

# 33. Lifecycle Operation History

Record meaningful lifecycle events.

Example:

```text
17:22:04 Model switch requested
17:22:05 Previous profile preserved
17:22:06 vLLM stopped
17:22:07 New profile applied
17:22:08 vLLM starting
17:22:35 Model loaded
17:22:39 KV cache initialized
17:22:42 Health check passed

SUCCESS
```

Capture failure information when applicable.

This should be easier to understand than raw container logs alone.

---

# 34. Logs

Provide access to appropriate operational logs:

* manager logs
* vLLM startup logs
* lifecycle operation logs
* benchmark logs

Provide:

* truncation
* tailing where useful
* reasonable size limits

Do not expose arbitrary unrelated host logs.

---

# 35. Benchmarking Is a Core Feature

Benchmarking is not an optional future enhancement.

The portal should make it easy to measure local models and tuning changes using standardized, reproducible tests.

Use official/reliable vLLM benchmark tooling where practical instead of implementing timing logic unnecessarily.

Prefer:

```text
vllm bench serve
```

or another supported vLLM benchmarking mechanism appropriate to the installed version.

---

# 36. Benchmark Types

At minimum support:

1. Interactive benchmark
2. Coding-context benchmark
3. Long-context benchmark
4. Concurrency benchmark
5. Prefix-cache benchmark

---

# 37. Interactive Benchmark

This should approximate interactive coding/agent usage.

Suggested baseline:

```text
Concurrency     1
Prompt          ~1K tokens
Output          ~256 tokens
```

Measure:

```text
TTFT P50
TTFT P95
TTFT P99

TPOT

ITL

E2E latency

Prompt tokens/sec
Output tokens/sec
```

---

# 38. Coding-Context Benchmark

Provide a benchmark representative of coding-agent workloads.

Example baseline:

```text
Prompt       8K tokens
Output       512 tokens
Concurrency  1
```

The prompt should be deterministic and reproducible.

---

# 39. Long-Context Benchmark

Support increasingly long actual prompts when the active configuration permits.

Example:

```text
1K
4K
8K
16K
32K
64K
```

Measure:

* TTFT
* prompt processing throughput
* generation throughput
* TPOT
* ITL
* end-to-end latency
* KV utilization
* VRAM consumption
* GPU utilization

Use deterministic tokenized input.

Do not estimate token count using character count.

---

# 40. Concurrency Benchmark

Test increasing concurrency such as:

```text
1
2
4
8
```

or safe alternatives appropriate to the configuration.

Measure:

* aggregate throughput
* request throughput
* TTFT
* TPOT
* latency degradation
* KV-cache utilization
* GPU utilization
* VRAM

This should expose the point where increased concurrency produces unacceptable latency.

---

# 41. Prefix-Cache Benchmark

Test repeated workloads that share a substantial common prefix.

This is particularly relevant to coding-agent workloads.

Compare:

```text
Cold TTFT
Warm TTFT
Prefix-cache hit rate
Prompt processing throughput
Overall latency improvement
```

Use reproducible input.

---

# 42. Benchmark Metrics

Persist and display where available:

```text
TTFT P50/P95/P99

TPOT P50/P95/P99

ITL P50/P95/P99

E2E P50/P95/P99

Prompt tokens/sec
Output tokens/sec
Requests/sec

GPU utilization
Peak GPU utilization

VRAM before
Peak VRAM
VRAM after

KV utilization before
Peak KV utilization
KV utilization after

Temperature
Power

Model startup/load time
```

---

# 43. Benchmark Memory Snapshots

Every benchmark should capture resource state.

## Before

Record:

```text
total VRAM
external/workstation VRAM
vLLM VRAM
KV utilization
GPU utilization
temperature
```

## During

Record:

```text
peak VRAM
peak KV utilization
peak GPU utilization
temperature
power where available
```

## After

Record:

```text
VRAM
KV utilization
GPU state
```

---

# 44. Workstation vs Dedicated Test Classification

Support benchmark classification such as:

```text
Dedicated GPU
Workstation coexistence
```

The manager does not need to launch browser or IDE workloads.

The classification simply identifies whether the benchmark was run while the GPU was also supporting normal workstation activity.

Capture external VRAM usage to make these comparisons meaningful.

---

# 45. Tuning Experiments

The portal should provide controlled experiments rather than automatic "magic" tuning.

At minimum support:

* context configuration sweep
* GPU-memory-utilization sweep
* concurrency sweep

Additional tuning dimensions may be added later.

---

# 46. Context Configuration Sweep

Allow testing configurations such as:

```text
8K
16K
32K
64K
```

Each step should:

```text
Preserve known-good configuration
        ↓
Apply test profile
        ↓
Restart vLLM
        ↓
Wait for health
        ↓
Capture startup memory state
        ↓
Benchmark
        ↓
Persist results
```

Record:

* requested context
* effective context
* model weight VRAM
* KV-cache VRAM
* KV capacity
* runtime VRAM
* headroom
* maximum concurrency
* TTFT
* prompt throughput
* decode throughput
* TPOT

---

# 47. GPU Memory Utilization Sweep

Allow testing values such as:

```text
0.75
0.80
0.85
0.90
0.95
```

For each test capture:

```text
Model weight VRAM
KV-cache VRAM
KV capacity
Runtime VRAM
External GPU usage
Remaining headroom

TTFT
Prompt tokens/sec
Output tokens/sec
TPOT
Concurrency capability
```

The purpose is to determine whether allocating more GPU memory produces a useful performance or capacity gain.

Do not assume higher utilization is automatically better.

---

# 48. Benchmark Reproducibility

Every benchmark must retain enough information to reproduce it.

Persist:

## Host

```text
host ID
hostname
OS
OS version
kernel
architecture
```

## GPU

```text
vendor
model
device count
devices used
VRAM
driver
```

## Compute Runtime

```text
ROCm version
or
CUDA version
```

## vLLM

```text
vLLM version
container image
deployment type
```

## Model

```text
model ID
model revision
architecture
quantization
dtype
```

## Profile

```text
max_model_len
gpu_memory_utilization
KV settings
max_num_seqs
max_num_batched_tokens
prefix caching
offload configuration
parallelism configuration
```

## Observed Runtime

```text
model weight VRAM
KV cache VRAM
KV token capacity
activation/runtime VRAM
backend/non-Torch VRAM
total vLLM VRAM
external GPU usage
headroom
```

## Benchmark

```text
benchmark type
prompt length
output length
concurrency
request count
warm-up count
seed where applicable
tool/version
```

## Results

```text
TTFT
TPOT
ITL
E2E
prompt throughput
generation throughput
request throughput
resource measurements
```

Also retain raw benchmark output where practical.

---

# 49. Benchmark Database

SQLite is the preferred initial database.

Use a persistent bind-mounted database file.

The manager container may contain the SQLite library, but the actual database must survive container recreation.

Do not introduce PostgreSQL unless a real requirement emerges.

The schema should use proper relational structures for core entities such as:

* host
* GPU/device
* model
* profile
* benchmark run
* benchmark metrics
* operation history

Raw JSON may be retained in addition to normalized values.

---

# 50. Benchmark History

Provide a searchable/filterable benchmark history.

Allow filtering by:

* host
* GPU
* model
* profile
* benchmark type
* context
* date
* tags
* workstation/dedicated classification

Allow notes and tags.

Example:

```text
Tags:
coding
interactive
workstation-safe

Notes:
Browser and IDE were running during benchmark.
```

---

# 51. Benchmark Comparison

Allow side-by-side comparison of:

* models
* profiles
* context lengths
* GPU-memory-utilization settings
* quantization
* hosts
* GPU models
* benchmark types

Useful columns include:

```text
Host
GPU
Model
Profile
Context

Weight VRAM
KV-cache VRAM
KV capacity
Runtime VRAM
Headroom

TTFT
Prompt tok/s
Decode tok/s
TPOT
```

Use simple charts where they meaningfully improve comparison.

Do not overbuild charting.

---

# 52. Model Performance Summary

For each tested model, build a useful summary from measured data.

Example structure:

```text
Qwen3-Coder-30B-A3B

Weights                 18.7 GiB
Configured context      32K
KV cache                 5.8 GiB
KV capacity              96K
VRAM headroom             4.1 GiB

Interactive TTFT P50    290 ms
Decode                    74 tok/s
Prompt processing      1,920 tok/s

Largest tested context    32K
```

Labels such as:

```text
Recommended
Workstation-safe
Best profile
```

must only come from explicit criteria or measured benchmark rules.

Do not assign subjective recommendations without defined logic.

---

# 53. Model Startup Performance

Record activation characteristics.

Capture where possible:

```text
restart requested
vLLM process/container start
model load completion
KV-cache initialization
API healthy
```

Derive useful values such as:

```text
model load time
time until healthy
```

Also capture startup memory state.

---

# 54. Frontend Information Architecture

Primary navigation should approximately be:

```text
Dashboard
Models
Profiles
Benchmarks
Compare
Operations / Logs
System
Settings
```

There must be **no Chat page**.

---

# 55. Frontend Design

The UI should feel like a professional infrastructure-management application.

Desired characteristics:

* clean
* concise
* responsive
* easy to scan
* useful information hierarchy
* clear health/status indicators
* well-designed tables
* sensible graphs
* confirmation around disruptive lifecycle actions
* useful warnings
* dark/light mode if practical

Avoid:

* generic CRUD-admin appearance
* excessive decoration
* unnecessary animations
* giant blocks of explanatory text
* showing raw implementation details to normal users

---

# 56. Authentication

Provide simple secure authentication suitable for LAN administration.

Do not allow authentication work to block core management functionality.

Requirements:

* no plaintext passwords
* secure password hashing
* session handling
* logout
* reasonable brute-force protection if practical
* secrets configured outside source control

Avoid unnecessary v1 complexity such as:

* OAuth infrastructure
* external identity providers
* enterprise RBAC
* multi-tenant account systems

Architecture should allow stronger authentication later.

---

# 57. Security

Treat the portal as an administrative application.

Requirements:

* validate all API inputs
* validate model IDs
* validate profile values
* validate paths
* prevent path traversal
* prevent command injection
* never concatenate untrusted input into shell commands
* no arbitrary host command endpoint
* no unrestricted container socket exposure
* least privilege
* secure secret handling
* sensible container security
* LAN-only/default-restricted exposure where appropriate

---

# 58. SELinux and RHEL/Fedora

Fedora and RHEL are first-class targets.

The portal must work with SELinux enforcing.

Do not solve permissions issues by disabling SELinux.

Never use:

```text
setenforce 0
```

as an installation strategy.

Handle container bind-mount labeling appropriately, including `:z` or `:Z` semantics where relevant.

Document required SELinux behavior.

---

# 59. AppArmor

On systems using AppArmor:

* detect it where practical
* do not disable AppArmor globally
* request only narrowly scoped changes if technically necessary

---

# 60. Graceful Degradation

Missing optional capabilities must not break the application.

Examples:

```text
Power telemetry: Unavailable

GPU clock telemetry: Unavailable

Client context: Not detected

Lifecycle control: Monitoring only

KV capacity: Not reported by this vLLM version
```

The application should remain useful with partial telemetry.

---

# 61. Health Checks

Provide a manager health endpoint.

At minimum report:

```text
manager application healthy
database accessible
host adapter status
vLLM reachable/unreachable
vLLM metrics reachable/unreachable
GPU telemetry available/unavailable
```

The manager itself should remain healthy if vLLM is intentionally stopped.

---

# 62. Deployment

The management application must itself be containerized.

Prefer one portable manager image rather than vendor-specific images.

Do not create separate images such as:

```text
vllm-manager-amd
vllm-manager-nvidia
vllm-manager-ubuntu
vllm-manager-rhel
```

unless proven technically necessary.

Persistent data should use explicit host storage/bind mounts.

---

# 63. Deployment Scripts

Provide or maintain scripts such as:

```text
scripts/preflight.sh
scripts/deploy.sh
scripts/healthcheck.sh
scripts/status.sh
scripts/backup.sh
scripts/uninstall.sh
```

Requirements:

* idempotent where appropriate
* clear error handling
* configurable by environment
* shellcheck clean
* safe defaults
* non-destructive preflight

---

# 64. Uninstall Safety

`uninstall.sh` must remove only management-portal resources.

It must never remove:

* the existing vLLM deployment
* vLLM container images
* local models
* Hugging Face cache
* unrelated container data
* unrelated host files

Persistent manager data should only be deleted with an explicit destructive option.

---

# 65. Testing

Automated testing is required.

## Unit Tests

Cover areas such as:

* profile validation
* model identifier validation
* path validation
* context validation
* native-context parsing
* unknown-context handling
* GPU capability detection
* AMD telemetry normalization
* NVIDIA telemetry normalization
* multi-GPU handling
* Docker detection
* Podman detection
* Quadlet detection
* SELinux detection
* vLLM lifecycle adapters
* KV-cache parsing
* memory-accounting parsing
* prevention of VRAM double counting
* benchmark parsing
* benchmark persistence
* command-injection protection

## Integration Tests

Cover:

* API health
* database operations
* simulated vLLM endpoint
* simulated metrics endpoint
* healthy/unhealthy vLLM
* profile lifecycle
* model-switch workflow with mocked lifecycle backend
* benchmark persistence
* capability discovery

Use mocked hardware/providers for platform combinations not physically available.

---

# 66. Supported Test Matrix

Design and test for combinations such as:

```text
Ubuntu + AMD
Ubuntu + NVIDIA
Fedora + AMD
Fedora + NVIDIA
RHEL + AMD
RHEL + NVIDIA
```

Also test:

```text
single GPU
multiple GPUs
no GPU
telemetry provider missing
monitoring-only vLLM
```

Physical hardware is not required for every CI test.

---

# 67. First Live Validation Host

`scar.lab` is the first live development and validation host.

Current first-target characteristics include:

```text
Ubuntu 24.04
AMD Radeon AI Pro R9700 32 GB
ROCm
existing containerized vLLM deployment
```

Scar-specific implementation details must remain behind adapters and must not become the general architecture.

Live testing on Scar must not break or replace its working vLLM/ROCm environment.

---

# 68. Documentation

Keep `README.md` concise and operational.

It should cover:

* project purpose
* architecture overview
* prerequisites
* install/deploy
* configuration
* accessing the portal
* supported platforms
* vLLM integration
* running tests
* backup
* uninstall

Use deeper documentation where necessary.

Recommended files include:

```text
docs/ARCHITECTURE.md
docs/SECURITY.md
docs/BENCHMARKING.md
docs/DEVELOPMENT.md
docs/PRODUCT_REQUIREMENTS.md
IMPLEMENTATION_STATUS.md
```

`GOALS.md` remains the authoritative high-level product specification.

---

# 69. Implementation Status Tracking

Maintain a concise implementation status file.

Example structure:

```text
Feature                         Status        Notes
---------------------------------------------------------------
Host discovery                  Complete      ...
AMD telemetry                   Partial       ...
NVIDIA telemetry                Complete      ...
Model discovery                 Missing       ...
Model download                  Missing       ...
Model switching                 Partial       ...
Profiles                        Complete      ...
Context tuning                  Partial       ...
KV-cache accounting             Missing       ...
Interactive benchmark          Missing       ...
Context sweep                  Missing       ...
GPU-memory sweep               Missing       ...
Benchmark comparison           Partial       ...
Last-known-good rollback        Missing       ...
Frontend dashboard             Partial       ...
```

Statuses should reflect working implementation rather than presence of interfaces or stubs.

---

# 70. Definition of Complete

A feature should not be classified as complete merely because an API endpoint, class, or UI stub exists.

Where applicable, completion means:

1. actual implementation exists
2. input validation exists
3. appropriate unit tests exist
4. appropriate integration tests exist
5. API behavior has been tested
6. frontend behavior works if user-facing
7. error handling works
8. documentation matches behavior
9. live non-destructive validation has been performed on supported available hardware where practical

---

# 71. End-to-End Definition of Done

The product is successful when a user can install the same management application on a supported vLLM host and:

1. identify the host OS and version
2. identify the kernel and architecture
3. identify AMD or NVIDIA GPUs
4. enumerate multiple GPUs
5. select the appropriate telemetry provider
6. display GPU utilization
7. display VRAM used/free/total
8. display temperature and power where supported
9. identify ROCm or CUDA
10. identify the vLLM deployment
11. connect to the vLLM API
12. connect to vLLM metrics
13. see the active model
14. see the active runtime profile
15. see configured context
16. see model-native context where known
17. see client context where detectable
18. see KV-cache memory
19. see KV-cache token capacity
20. see KV utilization
21. see detailed vLLM VRAM accounting
22. see external/workstation GPU usage
23. see remaining VRAM headroom
24. browse installed models
25. discover/download compatible models
26. view model metadata and storage usage
27. create runtime profiles
28. preflight a profile before activation
29. switch models safely
30. restart the existing vLLM deployment
31. detect successful startup
32. identify startup failure/OOM where possible
33. restore the last-known-good profile
34. run an interactive benchmark
35. run a coding-context benchmark
36. run long-context tests
37. run concurrency tests
38. run prefix-cache tests
39. perform context sweeps
40. perform GPU-memory-utilization sweeps
41. record TTFT
42. record prompt-processing throughput
43. record generation throughput
44. record TPOT/ITL/E2E latency
45. record GPU/VRAM/KV metrics during benchmarks
46. retain reproducible benchmark metadata
47. compare models
48. compare profiles
49. compare context configurations
50. compare GPU-memory configurations
51. compare different hosts and GPU hardware
52. review operation history and logs
53. use the portal in monitoring-only mode when lifecycle control is unavailable
54. run on SELinux-enforcing Fedora/RHEL without disabling SELinux
55. remove the manager without damaging the existing vLLM deployment

---

# 72. Product Priorities

When tradeoffs are required, prioritize in this order:

1. **Do not disrupt working vLLM deployments**
2. **Correctness of measurements and configuration**
3. **Safe lifecycle management**
4. **Portability**
5. **Useful model management**
6. **Reproducible benchmarking**
7. **Clear tuning visibility**
8. **Security**
9. **Maintainability**
10. **Frontend polish**

Avoid complexity that does not directly support these objectives.

---

# 73. Non-Goals

Unless requirements change, do not turn this project into:

* a chat application
* an Open WebUI replacement
* an inference API implementation
* a Kubernetes platform
* a Prometheus replacement
* a Grafana replacement
* a full enterprise identity platform
* an automatic GPU process killer
* an automatic ROCm/CUDA installer
* a GPU driver manager
* a vLLM upgrade manager
* a generic Linux administration portal
* an unrestricted container-management console
* a generic remote-shell product

---

# 74. Final Guiding Principle

The application should turn local vLLM management from:

```text
edit configuration
restart container
watch logs
guess at VRAM
run manual commands
record numbers somewhere
change another parameter
repeat
```

into:

```text
Select model
      ↓
Select/create profile
      ↓
Understand expected resource use
      ↓
Activate safely
      ↓
See actual VRAM/KV/context allocation
      ↓
Run standardized benchmark
      ↓
Tune one variable
      ↓
Benchmark again
      ↓
Compare measured results
      ↓
Save known-good configuration
```

The finished product should make **local-model operation, performance analysis, and vLLM tuning understandable, safe, repeatable, and portable across Linux systems and AMD/NVIDIA GPU environments.**
