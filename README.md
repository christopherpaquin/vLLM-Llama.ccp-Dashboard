# vLLM Management Portal

[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI 0.110](https://img.shields.io/badge/FastAPI-0.110-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![SQLite](https://img.shields.io/badge/Database-SQLite-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
![Tested on Ubuntu 24.04](https://img.shields.io/badge/Tested-Ubuntu%2024.04-E95420?logo=ubuntu&logoColor=white)
![Tested with AMD ROCm](https://img.shields.io/badge/Tested-AMD%20ROCm-ED1C24?logo=amd&logoColor=white)

An early-stage management and observability application for existing vLLM
deployments. The intended product provides portable host/GPU discovery, safe
runtime profiles and lifecycle operations, model management, detailed memory
accounting, and reproducible benchmarks. It is not a chat frontend.

> **Development status:** The repository contains a deployable FastAPI/SQLite
> backend foundation. Lifecycle execution remains disabled and the older
> mutation-provider prototypes must not be used on a production vLLM host. There is no
> frontend yet. See
> [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) for the verified feature
> matrix and [GOALS.md](GOALS.md) for the authoritative requirements.

## Architecture

The architecture keeps the existing vLLM deployment independent and
isolates platform-specific behavior behind system, GPU telemetry, container
runtime, and lifecycle providers. The current code establishes provider
interfaces, SQLAlchemy entities, and a versioned HTTP API. Read-only Linux,
AMD SMI/ROCm SMI, Docker Compose, and vLLM endpoint discovery have been live
validated on `scar.lab`.

## Deployment

The supported scar deployment requires Ubuntu 24.04, Docker Engine with the
Compose plugin, the existing ROCm installation, and a healthy vLLM endpoint.
No Python virtual environment is needed on the deployment host.

```bash
./scripts/deploy.sh
```

That one command validates prerequisites, creates `.env` from the committed
template when needed, builds the pinned portal image, starts the portal and its
read-only Docker API proxy, and waits for health. Open the API documentation at
`http://scar.lab:8088/docs` or query health at
`http://scar.lab:8088/api/v1/health`.

Both containers use Docker's `unless-stopped` restart policy. Because Docker is
enabled at boot on scar, the deployment starts after a reboot without a venv,
interactive shell, or separate systemd unit. The portal is isolated from the
existing vLLM Compose project and does not mount its configuration or model
cache.

Configuration belongs in the ignored `.env`; `.env-template` documents all
settings. Operational commands are:

```bash
./scripts/status.sh
./healthcheck.sh
./scripts/backup.sh
./scripts/uninstall.sh
```

Uninstall preserves `/var/lib/vllm-management-portal` by default. The explicit
`--purge-data` option permanently removes only that validated path. Neither mode
changes the vLLM deployment, image, or model cache.

## Development requirements

- Python 3.12
- A virtual environment
- SQLite (provided through Python)

AMD/NVIDIA tooling and a running vLLM service are not required for the unit/API
test suite. BATS is required for deployment-script tests.

## Development setup

```bash
python3.12 -m venv venv
venv/bin/pip install -r backend/requirements.txt
```

Start the development API from the backend directory:

```bash
cd backend
../venv/bin/uvicorn main:app --reload
```

The API is available at `http://localhost:8000`; interactive OpenAPI
documentation is at `http://localhost:8000/docs`.

The default database URL is `sqlite:///./vllm_portal.db`, resolved relative to
the process working directory. This is development behavior only and is not a
durable deployment configuration.

## Current API surface

- `GET /health` and `GET /api/v1/health`
- `GET /api/v1/capabilities` for a refreshed read-only host/runtime snapshot
- `POST /api/v1/runtime/sync` and `/runtime/snapshots` for observed state
- `POST /api/v1/runtime/known-good` for health-gated known-good records
- CRUD-like model and profile record endpoints under `/api/v1`
- benchmark record endpoints and a bounded `/api/v1/benchmarks/run` smoke test
- preliminary memory validation and storage endpoints

Request validation is currently implemented for model/profile creation and
updates and for the memory-validation endpoint. Other endpoints remain
unvalidated prototypes and are tracked as such in the implementation status.

## Testing

```bash
venv/bin/python -m pytest -q
bats tests/deployment.bats
```

The suite exercises request schemas, API integration, profile referential
checks, Linux/AMD/Docker/vLLM discovery parsers, state persistence, lifecycle
action preview, and basic benchmarking.

## Supported platforms

Ubuntu 24.04/26.04, Fedora, and RHEL with AMD or NVIDIA GPUs are product
targets. Ubuntu 24.04 with AMD SMI, Docker Compose, and the existing vLLM
deployment has been non-destructively validated on `scar.lab`; this is not yet
a general supported release.

See [the scar baseline](docs/SCAR_BASELINE.md) for collected values,
unavailable measurements, and lifecycle safety evidence.

## License

No license file has been added yet.
