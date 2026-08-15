"""Read-only host and existing-vLLM discovery."""

from __future__ import annotations

import json
import platform
import re
import shutil
import socket
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

import psutil

from .gpu_telemetry import AMDGPUProvider, GenericGPUProvider, NVGPUProvider


CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def run_read_only(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a bounded read-only discovery command."""
    return subprocess.run(
        command, capture_output=True, check=True, text=True, timeout=10
    )


def read_json(url: str, timeout: float = 3.0) -> tuple[bool, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 300, json.load(response)
    except (OSError, ValueError, urllib.error.URLError):
        return False, None


def read_text(url: str, timeout: float = 3.0) -> tuple[bool, str | None]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 300, response.read().decode("utf-8")
    except (OSError, UnicodeDecodeError, urllib.error.URLError):
        return False, None


class HostDiscovery:
    """Collect normalized, non-destructive Linux host capabilities."""

    def __init__(self, os_release: Path = Path("/etc/os-release")) -> None:
        self.os_release = os_release

    def discover(self) -> dict[str, Any]:
        release = self._read_os_release()
        memory = psutil.virtual_memory()
        root_storage = shutil.disk_usage("/")
        return {
            "hostname": socket.gethostname(),
            "os_id": release.get("ID", "unknown"),
            "os_name": release.get("NAME", "Unknown"),
            "os_version": release.get("VERSION_ID", "Unknown"),
            "kernel": platform.release(),
            "architecture": platform.machine(),
            "uptime_seconds": max(
                0,
                int(
                    psutil.boot_time()
                    and __import__("time").time() - psutil.boot_time()
                ),
            ),
            "cpu_logical_count": psutil.cpu_count(logical=True),
            "cpu_physical_count": psutil.cpu_count(logical=False),
            "memory_total_bytes": memory.total,
            "memory_available_bytes": memory.available,
            "root_storage_total_bytes": root_storage.total,
            "root_storage_free_bytes": root_storage.free,
            "selinux": self._selinux_status(),
            "apparmor": self._apparmor_status(),
        }

    def _read_os_release(self) -> dict[str, str]:
        try:
            lines = self.os_release.read_text(encoding="utf-8").splitlines()
        except OSError:
            return {}
        return {
            key: value.strip().strip('"')
            for line in lines
            if "=" in line
            for key, value in [line.split("=", 1)]
        }

    @staticmethod
    def _selinux_status() -> str:
        enforce = Path("/sys/fs/selinux/enforce")
        if not enforce.exists():
            return "not available"
        try:
            return "enforcing" if enforce.read_text().strip() == "1" else "permissive"
        except OSError:
            return "Unknown"

    @staticmethod
    def _apparmor_status() -> str:
        enabled = Path("/sys/module/apparmor/parameters/enabled")
        try:
            return (
                "enabled" if enabled.read_text().strip().lower() == "y" else "disabled"
            )
        except OSError:
            return "not available"


class DockerVLLMDiscovery:
    """Discover a Compose-managed vLLM container without changing it."""

    def __init__(self, runner: CommandRunner = run_read_only) -> None:
        self._run = runner

    def discover(self) -> dict[str, Any]:
        try:
            output = self._run(["docker", "ps", "--format", "{{json .}}"]).stdout
            containers = [
                json.loads(line) for line in output.splitlines() if line.strip()
            ]
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
            return {
                "runtime": "Unavailable",
                "lifecycle_mechanism": "Unknown",
                "container": None,
            }
        candidate = next(
            (
                item
                for item in containers
                if "vllm" in str(item.get("Names", "")).lower()
                or "vllm" in str(item.get("Image", "")).lower()
            ),
            None,
        )
        if not candidate:
            return {
                "runtime": "docker",
                "lifecycle_mechanism": "external/unknown",
                "container": None,
            }
        name = candidate.get("Names")
        try:
            inspected = json.loads(self._run(["docker", "inspect", str(name)]).stdout)[
                0
            ]
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError, IndexError):
            inspected = {}
        labels = inspected.get("Config", {}).get("Labels") or {}
        environment = self._safe_environment(
            inspected.get("Config", {}).get("Env") or []
        )
        mounts = inspected.get("Mounts") or []
        compose_file = labels.get("com.docker.compose.project.config_files")
        mechanism = "docker-compose" if compose_file else "docker"
        return {
            "runtime": "docker",
            "runtime_version": self._docker_version(),
            "lifecycle_mechanism": mechanism,
            "container": name,
            "container_id": inspected.get("Id"),
            "image": inspected.get("Config", {}).get("Image") or candidate.get("Image"),
            "running": inspected.get("State", {}).get("Running", False),
            "host_pid": inspected.get("State", {}).get("Pid"),
            "container_pids": self._container_pids(str(name)),
            "container_health": (inspected.get("State", {}).get("Health") or {}).get(
                "Status", "Unavailable"
            ),
            "started_at": inspected.get("State", {}).get("StartedAt"),
            "compose_project": labels.get("com.docker.compose.project"),
            "compose_file": compose_file,
            "compose_service": labels.get("com.docker.compose.service"),
            "environment": environment,
            "model_cache_location": next(
                (
                    mount.get("Source")
                    for mount in mounts
                    if mount.get("Destination")
                    == environment.get("HF_HOME", "/root/.cache/huggingface")
                ),
                None,
            ),
        }

    @staticmethod
    def _safe_environment(items: list[str]) -> dict[str, str]:
        allowed = {
            "MODEL_ID",
            "SERVED_MODEL_NAME",
            "MAX_MODEL_LEN",
            "GPU_MEMORY_UTILIZATION",
            "QUANTIZATION",
            "KV_CACHE_DTYPE",
            "KV_CACHE_MEMORY_BYTES",
            "EXTRA_VLLM_ARGS",
            "HF_HOME",
        }
        parsed = {}
        for item in items:
            key, separator, value = item.partition("=")
            if separator and key in allowed:
                parsed[key] = value
        return parsed

    def _docker_version(self) -> str:
        try:
            return self._run(
                ["docker", "version", "--format", "{{.Server.Version}}"]
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return "Unknown"

    def _container_pids(self, name: str) -> list[int]:
        try:
            output = self._run(["docker", "top", name, "-eo", "pid,comm"]).stdout
        except (OSError, subprocess.SubprocessError):
            return []
        pids = []
        for value in output.splitlines()[1:]:
            try:
                pids.append(int(value.split()[0]))
            except ValueError:
                continue
        return pids

    @staticmethod
    def lifecycle_preview(discovery: dict[str, Any]) -> dict[str, Any]:
        """Return exact proposed actions without executing them."""
        compose_file = discovery.get("compose_file")
        service = discovery.get("compose_service")
        if (
            discovery.get("lifecycle_mechanism") != "docker-compose"
            or not compose_file
            or not service
        ):
            return {
                "enabled": False,
                "reason": "validated Compose metadata unavailable",
                "actions": {},
            }
        base = ["docker", "compose", "-f", compose_file]
        return {
            "enabled": False,
            "reason": "preview only until configuration preservation and recovery are implemented",
            "actions": {
                "start": [*base, "up", "-d", service],
                "stop": [*base, "stop", service],
                "restart": [*base, "restart", service],
                "status": [*base, "ps", "--format", "json", service],
            },
        }


class VLLMEndpointDiscovery:
    """Read the OpenAI-compatible API and Prometheus metrics endpoints."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000") -> None:
        self.base_url = base_url.rstrip("/")

    def discover(self) -> dict[str, Any]:
        health_ok, _ = read_text(f"{self.base_url}/health")
        models_ok, models = read_json(f"{self.base_url}/v1/models")
        metrics_ok, metrics = read_text(f"{self.base_url}/metrics")
        first_model = ((models or {}).get("data") or [{}])[0] if models_ok else {}
        return {
            "api_healthy": health_ok and models_ok,
            "metrics_healthy": metrics_ok,
            "active_model": first_model.get("root") or first_model.get("id"),
            "served_model_name": first_model.get("id"),
            "configured_max_model_len": first_model.get("max_model_len"),
            "kv_cache_utilization_percent": self._metric(
                metrics, "vllm:kv_cache_usage_perc", multiplier=100
            ),
        }

    @staticmethod
    def _metric(text: str | None, name: str, multiplier: float = 1) -> float | None:
        if not text:
            return None
        pattern = re.compile(
            rf"^{re.escape(name)}(?:\{{[^}}]*\}})?\s+([-+0-9.eE]+)$", re.MULTILINE
        )
        match = pattern.search(text)
        return float(match.group(1)) * multiplier if match else None


class VLLMLogTelemetryParser:
    """Version-tolerant parser for known vLLM startup telemetry lines."""

    PATTERNS = {
        "model_weight_memory_gib": re.compile(
            r"Model loading took ([0-9.]+) GiB memory"
        ),
        "kv_cache_memory_gib": re.compile(r"Available KV cache memory: ([0-9.]+) GiB"),
        "kv_cache_capacity_tokens": re.compile(r"GPU KV cache size: ([0-9,]+) tokens"),
        "maximum_concurrency": re.compile(r"Maximum concurrency .*: ([0-9.]+)x"),
        "effective_max_model_len": re.compile(r"Using max model len ([0-9,]+)"),
        "vllm_version": re.compile(r"V1 LLM engine \(v([^\)]+)\)"),
    }

    @classmethod
    def parse(cls, logs: str) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, pattern in cls.PATTERNS.items():
            matches = pattern.findall(logs)
            if not matches:
                continue
            value = matches[-1].replace(",", "")
            result[key] = value if key == "vllm_version" else float(value)
        for integer_key in ("kv_cache_capacity_tokens", "effective_max_model_len"):
            if integer_key in result:
                result[integer_key] = int(result[integer_key])
        result["memory_source"] = "Reported by vLLM" if result else "Unavailable"
        result["runtime_activation_memory_gib"] = None
        result["backend_non_torch_memory_gib"] = None
        return result


class CapabilityDiscoveryService:
    """Compose normalized host, GPU, Docker, endpoint, and log evidence."""

    def __init__(self, runner: CommandRunner = run_read_only) -> None:
        self.runner = runner

    def discover(self) -> dict[str, Any]:
        docker = DockerVLLMDiscovery(self.runner).discover()
        gpu_provider = self._gpu_provider()
        gpus = [gpu.to_dict() for gpu in gpu_provider.get_gpu_devices()]
        endpoint = VLLMEndpointDiscovery().discover()
        logs = ""
        if docker.get("container"):
            try:
                completed = self.runner(
                    ["docker", "logs", "--tail", "2000", docker["container"]]
                )
                logs = completed.stdout + completed.stderr
            except (OSError, subprocess.SubprocessError):
                pass
        log_telemetry = VLLMLogTelemetryParser.parse(logs)
        processes = [process for gpu in gpus for process in gpu.get("processes", [])]
        vllm_pids = set(docker.get("container_pids") or [])
        vllm_process_vram = sum(
            process.get("vram_bytes") or 0
            for process in processes
            if process.get("pid") in vllm_pids
        )
        external_process_vram = sum(
            process.get("vram_bytes") or 0
            for process in processes
            if process.get("pid") not in vllm_pids
        )
        attributed_process_vram = vllm_process_vram + external_process_vram
        total_used = sum(gpu.get("vram_used") or 0 for gpu in gpus)
        return {
            "host": HostDiscovery().discover(),
            "gpus": gpus,
            "runtime": docker,
            "vllm": {**endpoint, **log_telemetry},
            "memory": {
                "vllm_process_vram_bytes": vllm_process_vram or None,
                "external_process_vram_bytes": external_process_vram,
                "unattributed_gpu_memory_bytes": max(
                    total_used - attributed_process_vram, 0
                )
                if gpus
                else None,
                "headroom_bytes": sum(gpu.get("vram_free") or 0 for gpu in gpus)
                if gpus
                else None,
                "source": "Measured" if gpus else "Unavailable",
            },
            "lifecycle_preview": DockerVLLMDiscovery.lifecycle_preview(docker),
        }

    @staticmethod
    def _gpu_provider() -> AMDGPUProvider | NVGPUProvider | GenericGPUProvider:
        if shutil.which("amd-smi") or shutil.which("rocm-smi"):
            return AMDGPUProvider()
        if shutil.which("nvidia-smi"):
            return NVGPUProvider()
        return GenericGPUProvider()
