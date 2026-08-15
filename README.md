# vLLM Dashboard

[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI 0.110](https://img.shields.io/badge/FastAPI-0.110-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker Compose](https://img.shields.io/badge/Deploy-Docker%20Compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)
![Tested on Ubuntu 24.04](https://img.shields.io/badge/Tested-Ubuntu%2024.04-E95420?logo=ubuntu&logoColor=white)
![Tested with AMD ROCm](https://img.shields.io/badge/Tested-AMD%20ROCm-ED1C24?logo=amd&logoColor=white)

A compact operations dashboard for observing, tuning, and benchmarking an
existing vLLM deployment. It is an infrastructure interface, not a chat UI.

## 🎯 What it shows

The landing page puts the current runtime first:

| Area | Information | Status |
| --- | --- | --- |
| Host | Hostname, primary IP, OS/kernel, CPU model, total RAM | ✅ Live |
| Model | Active repository, served name, API and metrics health | ✅ Live |
| GPU | Utilization, VRAM, temperature, power, headroom | ✅ Live on AMD SMI |
| KV cache | Utilization, allocation, token capacity, concurrency | ✅ Where vLLM reports it |
| Models | Complete repositories in the read-only Hugging Face cache | ✅ Live |
| Benchmark | TTFT, output tokens/second, end-to-end latency | ✅ Bounded streaming test |
| Switching | Activate a different cached model | ⚠️ Safety-locked |

Advanced vLLM configuration and memory detail stays collapsed until needed.
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
│ AMD SMI/ROCm  │  │ vLLM API, metrics, Docker │
│ host telemetry│  │ and read-only model cache │
└───────────────┘  └────────────────────────────┘
```

The portal runs separately from vLLM. It reads GPU devices, the configured
ROCm installation, vLLM endpoints, Docker metadata through a restricted
socket proxy, and the Hugging Face cache through a read-only mount. Lifecycle
mutations remain disabled until configuration preservation and rollback are
fully implemented.

Host identity comes from `.env`; deployment detects the primary IPv4 source
address with `ip route`. CPU and RAM come from read-only Linux `/proc` and
`psutil` data. GPU identity and utilization come from AMD SMI, with ROCm SMI
as the fallback provider.

## 🚀 Deploy

Requirements are Ubuntu 24.04, Docker Engine with the Compose plugin, a local
ROCm installation, and an existing vLLM endpoint.

```bash
./scripts/deploy.sh
```

The idempotent deploy command creates `.env` from `.env-template` when needed,
builds the pinned image, starts the stack, and waits for application health.
Open `http://scar.lab:8088/`. Both containers use `restart: unless-stopped`, so
the portal returns automatically when the Docker service starts at boot.

## ⚙️ Configuration

Edit the ignored `.env` and rerun `./scripts/deploy.sh`. Do not hand-edit the
running containers.

| Setting | Default | Purpose |
| --- | --- | --- |
| `PORTAL_PORT` | `8088` | Dashboard port |
| `PORTAL_DATA_DIR` | `/var/lib/vllm-management-portal` | Persistent SQLite data |
| `VLLM_BASE_URL` | `http://host.docker.internal:8000` | Existing vLLM API |
| `VLLM_HOSTNAME` | `vllm-host` | Host name displayed on the dashboard |
| `ROCM_PATH` | `/opt/rocm-7.2.2` | Host ROCm installation |
| `MODEL_CACHE_PATH` | `/var/lib/vllm/huggingface/hub` | Read-only model cache |
| `RESTART_POLICY` | `unless-stopped` | Docker restart behavior |

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

`uninstall.sh` preserves portal data. `uninstall.sh --purge-data` removes only
the validated portal data path. Neither operation changes the existing vLLM
deployment, image, configuration, or cached models.

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
