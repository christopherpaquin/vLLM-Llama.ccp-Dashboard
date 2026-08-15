# Infrence Engine Dashboard

[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI 0.110](https://img.shields.io/badge/FastAPI-0.110-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker Compose](https://img.shields.io/badge/Deploy-Docker%20Compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)
![Tested on Ubuntu 24.04](https://img.shields.io/badge/Tested-Ubuntu%2024.04-E95420?logo=ubuntu&logoColor=white)
![Tested with AMD ROCm](https://img.shields.io/badge/Tested-AMD%20ROCm-ED1C24?logo=amd&logoColor=white)

A compact operations dashboard for observing, tuning, and benchmarking an
existing vLLM or llama.cpp deployment. It is an infrastructure interface, not
a chat UI.

## 🎯 What it shows

The landing page puts the current runtime first:

| Area | Information | Status |
| --- | --- | --- |
| Host | Hostname, primary IP, OS/kernel, CPU model, total RAM | ✅ Live |
| Model | Active repository, served name, API and metrics health | ✅ Live |
| GPU | Utilization, VRAM, temperature, power, headroom | ✅ Live on AMD SMI |
| Engine | Configured vLLM or llama.cpp provider | ✅ Visible in the host tile |
| KV cache | Utilization, allocation, token capacity, concurrency | ✅ Where the backend reports it |
| Models | Hugging Face snapshots or local GGUF files | ✅ Read-only discovery |
| Benchmark | TTFT, output tokens/second, end-to-end latency | ✅ Bounded streaming test |
| Switching | Activate a different cached model | ⚠️ Safety-locked |

Advanced inference configuration and memory detail stays collapsed until needed.
Unavailable values are labeled explicitly rather than estimated.

## 🧭 How it works

```text
┌──────────────────────────┐
│ Browser dashboard :8088 │
└────────────┬─────────────┘
             │ normalized HTTP API
┌────────────▼─────────────┐
│ FastAPI portal           │
│ SQLite history           │
└──────┬───────────┬───────┘
       │           │
       │           └──────────────┐
┌──────▼────────┐  ┌──────────────▼─────────────┐
│ AMD SMI/ROCm  │  │ Inference API and Docker  │
│ host telemetry│  │ and read-only model cache │
└───────────────┘  └────────────────────────────┘
```

The dashboard runs separately from the inference server. It reads GPU devices,
the configured ROCm installation, backend endpoints, Docker metadata through a
restricted socket proxy, and the configured model directory through a
read-only mount. Lifecycle mutations remain disabled until configuration
preservation and rollback are fully implemented.

vLLM uses `/health`, `/v1/models`, `/metrics`, and its startup telemetry.
llama.cpp uses its official `/health`, `/v1/models`, `/props`, and optional
`/metrics` endpoints. Both use the OpenAI-compatible `/v1/completions` API for
the quick benchmark. See the
[official llama-server documentation](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).

Host identity comes from `.env`; deployment detects the primary IPv4 source
address with `ip route`. CPU and RAM come from read-only Linux `/proc` and
`psutil` data. GPU identity and utilization come from AMD SMI, with ROCm SMI
as the fallback provider. The host AMD GPU ID table is mounted read-only so
newer cards retain their exact product names inside the dashboard container.

## 🚀 Deploy

Requirements are Ubuntu 24.04, Docker Engine with the Compose plugin, a local
ROCm installation, and an existing vLLM or llama.cpp endpoint.

```bash
./scripts/deploy.sh
```

The idempotent deploy command creates `.env` from `.env-template` when needed,
builds the pinned image, starts the stack, and waits for application health.
Open `http://scar.lab:8088/`. Both containers use `restart: unless-stopped`, so
the portal returns automatically when the Docker service starts at boot.

The deployed containers are named `vllm-llama-cpp-dashboard` and
`vllm-llama-cpp-dashboard-docker-proxy`.

## ⚙️ Configuration

Edit the ignored `.env` and rerun `./scripts/deploy.sh`. Do not hand-edit the
running containers.

| Setting | Default | Purpose |
| --- | --- | --- |
| `PORTAL_PORT` | `8088` | Dashboard port |
| `PORTAL_DATA_DIR` | `/var/lib/vllm-management-portal` | Persistent SQLite data |
| `INFERENCE_BACKEND` | `vllm` | `vllm` or `llama_cpp` |
| `INFERENCE_BASE_URL` | `http://host.docker.internal:8000` | Inference server URL |
| `INFERENCE_HOSTNAME` | `inference-host` | Host name displayed on the dashboard |
| `ROCM_PATH` | `/opt/rocm-7.2.2` | Host ROCm installation |
| `AMDGPU_IDS_PATH` | `/opt/amdgpu/share/libdrm/amdgpu.ids` | Host AMD model-name table |
| `MODEL_CACHE_PATH` | `/var/lib/vllm/huggingface/hub` | HF cache or llama.cpp GGUF directory |
| `RESTART_POLICY` | `unless-stopped` | Docker restart behavior |

For a llama.cpp server, set the following in `.env`, then redeploy:

```dotenv
INFERENCE_BACKEND=llama_cpp
INFERENCE_HOSTNAME=llama.example.net
INFERENCE_BASE_URL=http://host.docker.internal:8080
MODEL_CACHE_PATH=/srv/llama-models
```

The configured directory is mounted read-only. llama.cpp Prometheus metrics
are optional and require `llama-server --metrics`; health, model identity,
properties, and benchmarks still work when metrics are disabled.

Runtime details are provider-specific. A llama.cpp deployment shows verified
llama.cpp settings such as context, quantization, parallel slots, GPU layers,
batching, build version, and its actual inference image; vLLM-only settings are
not displayed as unavailable llama.cpp values.

## 🧪 Benchmark

Select **Run TTFT + token rate test** on the dashboard. The portal sends one
deterministic, bounded streaming request to the active model and persists:

- time to first token;
- output tokens per second;
- end-to-end latency;
- prompt/output token counts and raw stream evidence.

This quick test verifies interactive behavior; it is not a percentile-based
load benchmark.

## 🛠️ Operations

```bash
./healthcheck.sh
./scripts/status.sh
./scripts/backup.sh
./scripts/uninstall.sh
```

`uninstall.sh` preserves dashboard data. `uninstall.sh --purge-data` removes
only the validated dashboard data path. Neither operation changes the existing
inference deployment, image, configuration, or cached models.

## 🧑‍💻 Development and tests

```bash
python3.12 -m venv venv
venv/bin/pip install -r backend/requirements-dev.txt
venv/bin/pytest -q
bats tests/deployment.bats
```

Start a development server with:

```bash
cd backend
../venv/bin/uvicorn main:app --reload
```

API documentation is available at `/docs`. See
[IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) for verified progress,
[GOALS.md](GOALS.md) for the authoritative specification, and
[docs/SCAR_BASELINE.md](docs/SCAR_BASELINE.md) for live scar evidence.

## 🔒 Safety

- ✅ Monitoring and benchmark operations are available.
- ✅ The model cache and host configuration are mounted read-only.
- ⚠️ Model activation and lifecycle mutations remain disabled.
- ❌ Authentication is not implemented; restrict network access accordingly.

## 📄 License

No license has been selected yet.
