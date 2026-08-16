"""Read-only host and existing-vLLM discovery."""

from __future__ import annotations

import json
import os
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
from .inference_config import (
    backend_display_name,
    inference_backend,
    inference_base_url,
    inference_hostname,
)


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

    def __init__(
        self, os_release: Path | None = None, cpuinfo: Path | None = None
    ) -> None:
        self.os_release = os_release or Path(
            os.getenv("HOST_OS_RELEASE_PATH", "/etc/os-release")
        )
        self.cpuinfo = cpuinfo or Path("/proc/cpuinfo")

    def discover(self) -> dict[str, Any]:
        release = self._read_os_release()
        memory = psutil.virtual_memory()
        root_storage = shutil.disk_usage("/")
        cpu_model = self._cpu_model()
        return {
            "hostname": inference_hostname() or socket.gethostname(),
            "primary_ip": os.getenv("HOST_PRIMARY_IP") or "Unknown",
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
            "cpu_model": cpu_model,
            "cpu_model_short": self._short_cpu_model(cpu_model),
            "memory_total_bytes": memory.total,
            "memory_available_bytes": memory.available,
            "root_storage_total_bytes": root_storage.total,
            "root_storage_free_bytes": root_storage.free,
            "selinux": self._selinux_status(),
            "apparmor": self._apparmor_status(),
        }

    def _cpu_model(self) -> str:
        try:
            for line in self.cpuinfo.read_text(encoding="utf-8").splitlines():
                if line.lower().startswith("model name") and ":" in line:
                    return line.split(":", 1)[1].strip()
        except OSError:
            pass
        return platform.processor() or "Unknown"

    @staticmethod
    def _short_cpu_model(model: str) -> str:
        """Remove vendor marks, core counts, and clock suffixes for display."""
        shortened = model.replace("(R)", "").replace("(TM)", "")
        shortened = re.sub(r"\s+\d+-Core Processor$", "", shortened)
        shortened = re.sub(r"\s+CPU(?:\s+@\s+.*)?$", "", shortened)
        shortened = re.sub(r"\s+Processor$", "", shortened)
        return " ".join(shortened.split()) or "Unknown"

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
    """Discover a Compose-managed inference container without changing it."""

    def __init__(
        self, runner: CommandRunner = run_read_only, backend: str = "vllm"
    ) -> None:
        self._run = runner
        self.backend = backend

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
        terms = (
            ("llama.cpp", "llama-cpp", "llamacpp", "llama-server")
            if self.backend == "llama_cpp"
            else ("vllm",)
        )
        candidates = [
            item
            for item in containers
            if not self._is_dashboard_container(item)
            if any(
                term
                in (
                    str(item.get("Names", "")) + " " + str(item.get("Image", ""))
                ).lower()
                for term in terms
            )
        ]
        # Prefer the inference server over this management portal. Both names
        # intentionally contain "vllm", so first-match discovery is unsafe.
        candidate = max(
            candidates,
            key=lambda item: self._candidate_score(item, self.backend),
            default=None,
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
                    if self._is_model_cache_mount(mount, environment, self.backend)
                ),
                None,
            ),
            "backend_version": labels.get("org.opencontainers.image.version"),
        }

    @staticmethod
    def _is_dashboard_container(item: dict[str, Any]) -> bool:
        text = (
            f"{item.get('Names', '')} {item.get('Image', '')} "
            f"{item.get('Labels', '')}"
        ).lower()
        return "vllm-management-portal" in text or "dashboard-docker-proxy" in text

    @staticmethod
    def _is_model_cache_mount(
        mount: dict[str, Any], environment: dict[str, str], backend: str
    ) -> bool:
        destination = str(mount.get("Destination", ""))
        if backend == "llama_cpp":
            model_path = environment.get("LLAMA_ARG_MODEL", "")
            return bool(model_path) and destination == str(Path(model_path).parent)
        return destination == environment.get("HF_HOME", "/root/.cache/huggingface")

    @staticmethod
    def _candidate_score(item: dict[str, Any], backend: str = "vllm") -> int:
        name = str(item.get("Names", "")).lower()
        image = str(item.get("Image", "")).lower()
        score = 0
        if name == "vllm":
            score += 100
        if image.startswith("rocm/vllm") or image.startswith("vllm/vllm"):
            score += 50
        if backend == "llama_cpp":
            if name in {"llamacpp", "llama-cpp", "llama-server"}:
                score += 150
            if "llama-server" in name or "llama.cpp" in image or "llama-cpp" in image:
                score += 100
        if "management" in name or "management" in image or "portal" in name:
            score -= 100
        return score

    @staticmethod
    def _safe_environment(items: list[str]) -> dict[str, str]:
        allowed = {
            # Common & vLLM
            "MODEL_ID",
            "SERVED_MODEL_NAME",
            "MAX_MODEL_LEN",
            "GPU_MEMORY_UTILIZATION",
            "QUANTIZATION",
            "KV_CACHE_DTYPE",
            "KV_CACHE_MEMORY_BYTES",
            "EXTRA_VLLM_ARGS",
            "HF_HOME",
            "DTYPE",
            "MAX_NUM_SEQS",
            "MAX_NUM_BATCHED_TOKENS",
            "ENABLE_PREFIX_CACHING",
            "CPU_OFFLOAD_GB",
            "SWAP_SPACE",
            "TENSOR_PARALLEL_SIZE",
            "PIPELINE_PARALLEL_SIZE",
            "DATA_PARALLEL_SIZE",
            "ENABLE_CHUNKED_PREFILL",
            "VLLM_ENABLE_CHUNKED_PREFILL",
            "ENFORCE_EAGER",
            "SPECULATIVE_MODEL",
            "NUM_SPECULATIVE_TOKENS",
            "SPECULATIVE_DRAFT_TENSOR_PARALLEL_SIZE",
            "VLLM_ATTENTION_BACKEND",
            # llama.cpp
            "LLAMA_ARG_MODEL",
            "LLAMA_ARG_CTX_SIZE",
            "LLAMA_ARG_N_GPU_LAYERS",
            "LLAMA_ARG_BATCH",
            "LLAMA_ARG_UBATCH",
            "LLAMA_ARG_PARALLEL",
            "LLAMA_ARG_THREADS",
            "LLAMA_ARG_FLASH_ATTN",
            "LLAMA_ARG_CACHE_TYPE_K",
            "LLAMA_ARG_CACHE_TYPE_V",
            "LLAMA_ARG_KV_OFFLOAD",
            "LLAMA_ARG_KV_UNIFIED",
            "LLAMA_ARG_CACHE_RAM",
            "LLAMA_ARG_CACHE_PROMPT",
            "LLAMA_ARG_CACHE_REUSE",
            "LLAMA_ARG_ENDPOINT_METRICS",
            "LLAMA_ARG_SPECULATIVE",
            "LLAMA_ARG_DRAFT_MAX",
            "LLAMA_ARG_DRAFT_MIN",
            "LLAMA_ARG_DRAFT_P_MIN",
            "LLAMA_ARG_TEMP",
            "LLAMA_ARG_TOP_K",
            "LLAMA_ARG_TOP_P",
            "LLAMA_ARG_MIN_P",
            "LLAMA_ARG_REPEAT_PENALTY",
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
            "backend_type": "vllm",
            "backend_name": "vLLM",
            "api_healthy": health_ok and models_ok,
            "metrics_healthy": metrics_ok,
            "active_model": first_model.get("root") or first_model.get("id"),
            "served_model_name": first_model.get("id"),
            "configured_max_model_len": first_model.get("max_model_len"),
            "kv_cache_utilization_percent": self._metric(
                metrics, "vllm:kv_cache_usage_perc", multiplier=100
            )
            or self._metric(metrics, "vllm:gpu_cache_usage_factor", multiplier=100),
            "prompt_tokens_per_second": self._metric(
                metrics, "vllm:avg_prompt_throughput_tok_per_s"
            ),
            "output_tokens_per_second": self._metric(
                metrics, "vllm:avg_generation_throughput_tok_per_s"
            ),
            "num_requests_running": self._metric(metrics, "vllm:num_requests_running"),
            "num_requests_waiting": self._metric(metrics, "vllm:num_requests_waiting"),
            "num_requests_swapped": self._metric(metrics, "vllm:num_requests_swapped"),
            "prefix_cache_hit_rate": self._metric(
                metrics, "vllm:prefix_cache_hit_rate", multiplier=100
            ),
            "spec_decode_draft_acceptance_rate": self._metric(
                metrics, "vllm:spec_decode_draft_acceptance_rate", multiplier=100
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


class LlamaCppEndpointDiscovery:
    """Read llama.cpp's public health, model, properties, slots, and metrics APIs."""

    def __init__(self, base_url: str = "http://127.0.0.1:8080") -> None:
        self.base_url = base_url.rstrip("/")

    def discover(self) -> dict[str, Any]:
        health_ok, _ = read_json(f"{self.base_url}/health")
        models_ok, models = read_json(f"{self.base_url}/v1/models")
        props_ok, props = read_json(f"{self.base_url}/props")
        slots_ok, slots = read_json(f"{self.base_url}/slots")
        metrics_ok, metrics = read_text(f"{self.base_url}/metrics")
        first_model = ((models or {}).get("data") or [{}])[0] if models_ok else {}
        meta = first_model.get("meta") or {}
        settings = (props or {}).get("default_generation_settings") or {}
        params = settings.get("params") or {}
        total_slots = (props or {}).get("total_slots")
        n_ctx = settings.get("n_ctx") or meta.get("n_ctx")

        kv_capacity: int | None = None
        if slots_ok and isinstance(slots, list) and slots:
            slot_caps = [
                int(s["n_ctx"])
                for s in slots
                if isinstance(s, dict) and "n_ctx" in s and str(s["n_ctx"]).isdigit()
            ]
            if slot_caps:
                kv_capacity = sum(slot_caps)
        if kv_capacity is None and n_ctx is not None:
            slots_count = (
                total_slots if isinstance(total_slots, int) and total_slots > 0 else 1
            )
            kv_capacity = int(n_ctx) * slots_count

        kv_utilization: float | None = None
        prom_ratio = VLLMEndpointDiscovery._metric(
            metrics, "llamacpp:kv_cache_usage_ratio", multiplier=100
        )
        if prom_ratio is None:
            prom_ratio = VLLMEndpointDiscovery._metric(
                metrics, "llamacpp_kv_cache_usage_ratio", multiplier=100
            )

        if prom_ratio is not None:
            kv_utilization = round(prom_ratio, 2)
        elif slots_ok and isinstance(slots, list) and kv_capacity and kv_capacity > 0:
            active_tokens = 0
            for s in slots:
                if isinstance(s, dict):
                    if s.get("is_processing"):
                        active_tokens += int(s.get("n_prompt_tokens") or 0)
                    else:
                        active_tokens += int(s.get("n_prompt_tokens_cache") or 0)
            kv_utilization = round((active_tokens / kv_capacity) * 100, 2)

        acceptance_rate = VLLMEndpointDiscovery._metric(
            metrics, "llamacpp:speculative_acceptance_ratio", multiplier=100
        )
        if acceptance_rate is None:
            acceptance_rate = VLLMEndpointDiscovery._metric(
                metrics, "llamacpp_speculative_acceptance_ratio", multiplier=100
            )

        return {
            "backend_type": "llama_cpp",
            "backend_name": "llama.cpp",
            "api_healthy": health_ok and models_ok,
            "metrics_healthy": metrics_ok,
            "metrics_optional": True,
            "active_model": first_model.get("id"),
            "served_model_name": first_model.get("id"),
            "configured_max_model_len": n_ctx,
            "native_context_tokens": meta.get("n_ctx_train"),
            "model_parameters": meta.get("n_params"),
            "model_size_bytes": meta.get("size"),
            "model_quantization": (props or {}).get("model_ftype") or meta.get("ftype"),
            "maximum_concurrency": total_slots
            or (len(slots) if slots_ok and isinstance(slots, list) else None),
            "backend_version": (props or {}).get("build_info"),
            "kv_cache_capacity_tokens": kv_capacity,
            "kv_cache_utilization_percent": kv_utilization,
            "prompt_tokens_per_second": VLLMEndpointDiscovery._metric(
                metrics, "llamacpp:prompt_tokens_seconds"
            )
            or VLLMEndpointDiscovery._metric(metrics, "llamacpp_prompt_tokens_seconds"),
            "output_tokens_per_second": VLLMEndpointDiscovery._metric(
                metrics, "llamacpp:predicted_tokens_seconds"
            )
            or VLLMEndpointDiscovery._metric(
                metrics, "llamacpp_predicted_tokens_seconds"
            ),
            "flash_attention": (props or {}).get("flash_attn"),
            "speculative_acceptance_rate": acceptance_rate,
            "prompt_cache_hits": VLLMEndpointDiscovery._metric(
                metrics, "llamacpp:prompt_cache_hits_total"
            )
            or VLLMEndpointDiscovery._metric(
                metrics, "llamacpp_prompt_cache_hits_total"
            ),
            "prompt_cache_misses": VLLMEndpointDiscovery._metric(
                metrics, "llamacpp:prompt_cache_misses_total"
            )
            or VLLMEndpointDiscovery._metric(
                metrics, "llamacpp_prompt_cache_misses_total"
            ),
            "properties_healthy": props_ok,
            "slots_healthy": slots_ok,
            "generation_settings": {
                key: params.get(key)
                for key in (
                    "temperature",
                    "top_k",
                    "top_p",
                    "min_p",
                    "repeat_penalty",
                    "presence_penalty",
                    "frequency_penalty",
                    "seed",
                )
                if key in params
            },
        }


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
        "vllm_version": re.compile(
            r"V1 LLM engine \(v([^\)]+)\)|vLLM version ([0-9a-zA-Z.+_-]+)"
        ),
        "gpu_blocks": re.compile(r"# GPU blocks: ([0-9,]+)"),
        "chunked_prefill": re.compile(r"chunked prefill is ([a-zA-Z]+)"),
        "prefix_caching": re.compile(r"prefix caching is ([a-zA-Z]+)"),
    }

    @classmethod
    def parse(cls, logs: str) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, pattern in cls.PATTERNS.items():
            matches = pattern.findall(logs)
            if not matches:
                continue
            matched = matches[-1]
            if isinstance(matched, tuple):
                matched = next((m for m in matched if m), "")
            value = str(matched).replace(",", "")
            if key in ("vllm_version", "chunked_prefill", "prefix_caching"):
                result[key] = value
            else:
                try:
                    result[key] = float(value)
                except ValueError:
                    pass
        for integer_key in (
            "kv_cache_capacity_tokens",
            "effective_max_model_len",
            "gpu_blocks",
        ):
            if integer_key in result:
                result[integer_key] = int(result[integer_key])
        result["memory_source"] = "Reported by vLLM" if result else "Unavailable"
        result["runtime_activation_memory_gib"] = None
        result["backend_non_torch_memory_gib"] = None
        return result


def build_normalized_configuration(
    backend_type: str,
    inference: dict[str, Any],
    docker: dict[str, Any],
    gpus: list[dict[str, Any]],
    memory: dict[str, Any],
) -> dict[str, Any]:
    """Construct a clean, educational, normalized configuration structure."""
    env = docker.get("environment", {})
    gpu = gpus[0] if gpus else {}
    generation = inference.get("generation_settings", {})
    backend_name = "llama.cpp" if backend_type == "llama_cpp" else "vLLM"

    def fmt_gib(b: float | int | None) -> str:
        return f"{b / 1073741824:.1f} GiB" if b is not None else "Unavailable"

    def fmt_pct(p: float | int | None) -> str:
        return f"{float(p):.0f}%" if p is not None else "Unavailable"

    # 1. MODEL
    model_name = (
        inference.get("active_model")
        or env.get("MODEL_ID")
        or env.get("LLAMA_ARG_MODEL")
    )
    quant = (
        inference.get("model_quantization")
        or env.get("QUANTIZATION")
        or (env.get("DTYPE") if backend_type == "vllm" else None)
    )
    model_size_str = (
        fmt_gib(inference.get("model_size_bytes"))
        if inference.get("model_size_bytes")
        else (
            f"{inference.get('model_weight_memory_gib'):.1f} GiB"
            if inference.get("model_weight_memory_gib")
            else "Unavailable"
        )
    )
    model_items = [
        {
            "key": "model",
            "label": "Model",
            "value": model_name,
            "formatted": model_name or "Unavailable",
            "source": "runtime"
            if inference.get("active_model")
            else ("configured" if model_name else "unavailable"),
            "tooltip": "Model currently loaded by the inference engine.",
        },
        {
            "key": "engine",
            "label": "Inference Engine",
            "value": backend_name,
            "formatted": backend_name,
            "source": "runtime",
            "tooltip": "Backend currently serving the model. Different engines expose different performance and memory controls.",
        },
        {
            "key": "quantization",
            "label": "Quantization",
            "value": quant,
            "formatted": quant or "Full precision / Unquantized",
            "source": "runtime"
            if inference.get("model_quantization")
            else ("configured" if quant else "unavailable"),
            "tooltip": "Numeric precision used for model weights. Lower precision reduces VRAM and can improve speed, but may slightly reduce model accuracy.",
        },
        {
            "key": "model_size",
            "label": "Model Size",
            "value": inference.get("model_size_bytes")
            or (
                inference.get("model_weight_memory_gib", 0) * 1024**3
                if inference.get("model_weight_memory_gib")
                else None
            ),
            "formatted": model_size_str,
            "source": "runtime"
            if (
                inference.get("model_size_bytes")
                or inference.get("model_weight_memory_gib")
            )
            else "unavailable",
            "tooltip": "Size of the model weights. Larger models generally require more memory and memory bandwidth.",
        },
    ]

    # 2. CONTEXT & MEMORY
    ctx_val = inference.get("configured_max_model_len") or env.get(
        "LLAMA_ARG_CTX_SIZE" if backend_type == "llama_cpp" else "MAX_MODEL_LEN"
    )
    native_ctx = inference.get("native_context_tokens")
    kv_cap = inference.get("kv_cache_capacity_tokens")
    kv_util = inference.get("kv_cache_utilization_percent")
    vram_used = gpu.get("vram_used")
    vram_total = gpu.get("vram_total")
    vram_used_pct = (
        (vram_used / vram_total * 100) if (vram_used and vram_total) else None
    )
    vram_usage_str = (
        f"{vram_used/1073741824:.1f} / {vram_total/1073741824:.1f} GiB ({vram_used_pct:.0f}%)"
        if (vram_used and vram_total)
        else "Unavailable"
    )

    context_items = [
        {
            "key": "context_window",
            "label": "Context Window",
            "value": ctx_val,
            "formatted": f"{int(ctx_val):,} tokens" if ctx_val else "Unavailable",
            "source": "runtime"
            if inference.get("configured_max_model_len")
            else ("configured" if ctx_val else "unavailable"),
            "tooltip": "Maximum number of tokens the model can retain in the active conversation. Larger context consumes more KV-cache memory.",
        },
        {
            "key": "native_context",
            "label": "Native Model Context",
            "value": native_ctx,
            "formatted": f"{int(native_ctx):,} tokens" if native_ctx else "Unavailable",
            "source": "runtime" if native_ctx else "unavailable",
            "tooltip": "Maximum context length supported by the model architecture before runtime limits are applied.",
        },
    ]

    if backend_type == "llama_cpp":
        k_type = env.get("LLAMA_ARG_CACHE_TYPE_K") or "f16"
        v_type = env.get("LLAMA_ARG_CACHE_TYPE_V") or "f16"
        context_items.extend(
            [
                {
                    "key": "kv_cache_type_k",
                    "label": "KV Cache K Type",
                    "value": k_type,
                    "formatted": str(k_type).upper(),
                    "source": "configured"
                    if env.get("LLAMA_ARG_CACHE_TYPE_K")
                    else "default",
                    "tooltip": "Precision used to store key vectors in the attention cache. Lower precision reduces VRAM use with a possible small quality tradeoff.",
                },
                {
                    "key": "kv_cache_type_v",
                    "label": "KV Cache V Type",
                    "value": v_type,
                    "formatted": str(v_type).upper(),
                    "source": "configured"
                    if env.get("LLAMA_ARG_CACHE_TYPE_V")
                    else "default",
                    "tooltip": "Precision used to store value vectors in the attention cache. Lower precision reduces KV-cache memory consumption.",
                },
            ]
        )
    else:
        gpu_mem_target = env.get("GPU_MEMORY_UTILIZATION")
        kv_dtype = env.get("KV_CACHE_DTYPE") or "auto"
        kv_alloc_gib = inference.get("kv_cache_memory_gib")
        context_items.extend(
            [
                {
                    "key": "gpu_memory_utilization",
                    "label": "GPU Memory Target",
                    "value": gpu_mem_target,
                    "formatted": f"{float(gpu_mem_target):.2f} ({float(gpu_mem_target)*100:.0f}%)"
                    if gpu_mem_target
                    else "Unavailable",
                    "source": "configured" if gpu_mem_target else "unavailable",
                    "tooltip": "Fraction of GPU VRAM vLLM is allowed to reserve for model weights, KV cache, and runtime allocations.",
                },
                {
                    "key": "kv_cache_dtype",
                    "label": "KV Cache Dtype",
                    "value": kv_dtype,
                    "formatted": str(kv_dtype),
                    "source": "configured" if env.get("KV_CACHE_DTYPE") else "default",
                    "tooltip": "Precision used by the attention KV cache. Lower precision reduces memory use and may allow more context or concurrent requests.",
                },
                {
                    "key": "kv_cache_size",
                    "label": "KV Cache Allocation",
                    "value": kv_alloc_gib,
                    "formatted": f"{kv_alloc_gib:.2f} GiB"
                    if kv_alloc_gib is not None
                    else "Unavailable",
                    "source": "runtime" if kv_alloc_gib is not None else "unavailable",
                    "tooltip": "Memory available for storing attention state from active requests. KV-cache capacity determines how much context and concurrency can be supported.",
                },
            ]
        )

    context_items.extend(
        [
            {
                "key": "kv_cache_capacity",
                "label": "KV Cache Capacity",
                "value": kv_cap,
                "formatted": f"{int(kv_cap):,} tokens" if kv_cap else "Unavailable",
                "source": "runtime" if kv_cap else "unavailable",
                "tooltip": "Total capacity of the key-value cache measured in sequence tokens across all active slots.",
            },
            {
                "key": "kv_cache_utilization",
                "label": "KV Cache Utilization",
                "value": kv_util,
                "formatted": f"{kv_util:.1f}%"
                if kv_util is not None
                else "Unavailable",
                "source": "runtime" if kv_util is not None else "unavailable",
                "tooltip": "Current percentage of the KV cache actively holding prompt and response token state.",
            },
            {
                "key": "vram_usage",
                "label": "GPU VRAM Usage",
                "value": vram_used,
                "formatted": vram_usage_str,
                "source": "measured",
                "tooltip": "GPU memory currently used by model weights, KV cache, runtime buffers, and inference overhead.",
            },
            {
                "key": "vram_headroom",
                "label": "VRAM Headroom",
                "value": memory.get("headroom_bytes"),
                "formatted": fmt_gib(memory.get("headroom_bytes")),
                "source": "measured",
                "tooltip": "Measured free device memory remaining on the GPU.",
            },
            {
                "key": "process_vram",
                "label": "Inference GPU Memory",
                "value": memory.get("vllm_process_vram_bytes"),
                "formatted": fmt_gib(memory.get("vllm_process_vram_bytes")),
                "source": "measured",
                "tooltip": "GPU VRAM directly attributed to the inference engine process.",
            },
        ]
    )

    # 3. SCHEDULING / CONCURRENCY & BATCHING
    scheduling_items = []
    if backend_type == "llama_cpp":
        slots = (
            inference.get("maximum_concurrency") or env.get("LLAMA_ARG_PARALLEL") or 1
        )
        n_layers = env.get("LLAMA_ARG_N_GPU_LAYERS")
        batch = env.get("LLAMA_ARG_BATCH")
        ubatch = env.get("LLAMA_ARG_UBATCH")
        scheduling_items = [
            {
                "key": "parallel_slots",
                "label": "Parallel Slots",
                "value": slots,
                "formatted": str(slots),
                "source": "runtime"
                if inference.get("maximum_concurrency")
                else "configured",
                "tooltip": "Number of requests llama.cpp can process concurrently. More slots improve concurrency but consume additional KV-cache memory and may increase latency for a single user.",
            },
            {
                "key": "gpu_layers",
                "label": "GPU Layers",
                "value": n_layers,
                "formatted": "All layers GPU resident (99)"
                if str(n_layers) in ("99", "all", "All")
                else (f"{n_layers} layers" if n_layers else "Unavailable"),
                "source": "configured" if n_layers else "unavailable",
                "tooltip": "Number of model layers offloaded to the GPU. Full GPU offload is normally much faster than processing layers on the CPU.",
            },
            {
                "key": "batch_size",
                "label": "Batch Size",
                "value": batch,
                "formatted": f"{int(batch):,} tokens"
                if batch
                else "2,048 tokens (Default)",
                "source": "configured" if batch else "default",
                "tooltip": "Maximum number of prompt tokens processed together. Larger batches can improve prompt-processing throughput but require more memory.",
            },
            {
                "key": "ubatch_size",
                "label": "Microbatch Size (ubatch)",
                "value": ubatch,
                "formatted": f"{int(ubatch):,} tokens"
                if ubatch
                else "512 tokens (Default)",
                "source": "configured" if ubatch else "default",
                "tooltip": "Number of tokens processed by the GPU in each physical compute batch. Larger values can improve throughput but increase memory use and are not always faster.",
            },
        ]
    else:
        max_seqs = env.get("MAX_NUM_SEQS") or 4
        max_batched = env.get("MAX_NUM_BATCHED_TOKENS") or "auto"
        tp_size = env.get("TENSOR_PARALLEL_SIZE") or 1
        pp_size = env.get("PIPELINE_PARALLEL_SIZE") or 1
        dp_size = env.get("DATA_PARALLEL_SIZE") or 1
        cpu_offload = env.get("CPU_OFFLOAD_GB") or 0
        swap = env.get("SWAP_SPACE") or 4
        scheduling_items = [
            {
                "key": "max_num_seqs",
                "label": "Max Number of Sequences",
                "value": max_seqs,
                "formatted": str(max_seqs),
                "source": "configured" if env.get("MAX_NUM_SEQS") else "default",
                "tooltip": "Maximum number of active sequences vLLM may process concurrently. Higher values increase concurrency but consume more KV-cache memory.",
            },
            {
                "key": "max_num_batched_tokens",
                "label": "Max Batched Tokens",
                "value": max_batched,
                "formatted": f"{int(max_batched):,} tokens"
                if str(max_batched).isdigit()
                else str(max_batched),
                "source": "configured"
                if env.get("MAX_NUM_BATCHED_TOKENS")
                else "default",
                "tooltip": "Maximum number of tokens vLLM can combine into a scheduling batch. Larger values can improve throughput but increase resource usage.",
            },
            {
                "key": "tensor_parallel_size",
                "label": "Tensor Parallel Size",
                "value": tp_size,
                "formatted": str(tp_size),
                "source": "configured"
                if env.get("TENSOR_PARALLEL_SIZE")
                else "default",
                "tooltip": "Number of GPUs used to split model tensor operations. Values above 1 distribute the model across multiple GPUs.",
            },
            {
                "key": "pipeline_parallel_size",
                "label": "Pipeline Parallel Size",
                "value": pp_size,
                "formatted": str(pp_size),
                "source": "configured"
                if env.get("PIPELINE_PARALLEL_SIZE")
                else "default",
                "tooltip": "Number of pipeline stages used to distribute model layers across GPUs.",
            },
            {
                "key": "data_parallel_size",
                "label": "Data Parallel Size",
                "value": dp_size,
                "formatted": str(dp_size),
                "source": "configured" if env.get("DATA_PARALLEL_SIZE") else "default",
                "tooltip": "Number of independent model replicas used to process requests concurrently.",
            },
            {
                "key": "cpu_offload_gb",
                "label": "CPU Offload",
                "value": cpu_offload,
                "formatted": f"{cpu_offload} GiB",
                "source": "configured" if env.get("CPU_OFFLOAD_GB") else "default",
                "tooltip": "VRAM overflow space offloaded to host system RAM in GiB.",
            },
            {
                "key": "swap_space",
                "label": "Swap Space",
                "value": swap,
                "formatted": f"{swap} GiB",
                "source": "configured" if env.get("SWAP_SPACE") else "default",
                "tooltip": "CPU RAM swap space allocated per GPU in GiB.",
            },
        ]

    # 4. ATTENTION & CACHE
    attention_items = []
    flash_attn = (
        env.get("LLAMA_ARG_FLASH_ATTN")
        if backend_type == "llama_cpp"
        else env.get("VLLM_ATTENTION_BACKEND")
    )
    flash_attn_formatted = (
        "On (Auto)"
        if str(flash_attn).lower() in ("auto", "1", "true", "on")
        else (str(flash_attn) if flash_attn else "Auto")
    )
    attention_items.append(
        {
            "key": "flash_attention",
            "label": "Flash Attention",
            "value": flash_attn or "auto",
            "formatted": flash_attn_formatted,
            "source": "configured" if flash_attn else "runtime",
            "tooltip": "Optimized attention implementation that can reduce memory use and improve prompt processing. Performance depends on the GPU and backend.",
        }
    )

    if backend_type == "llama_cpp":
        prompt_cache_flag = env.get("LLAMA_ARG_CACHE_PROMPT")
        prompt_caching = (
            "Enabled"
            if prompt_cache_flag in (None, "", "1", "true", "True")
            else "Disabled"
        )
        kv_offload = (
            "Enabled"
            if env.get("LLAMA_ARG_KV_OFFLOAD") in ("1", "true", "True")
            else "Disabled"
        )
        kv_unified = (
            "Enabled"
            if env.get("LLAMA_ARG_KV_UNIFIED") in ("1", "true", "True")
            else "Disabled"
        )
        cache_ram = env.get("LLAMA_ARG_CACHE_RAM")
        attention_items.extend(
            [
                {
                    "key": "prompt_caching",
                    "label": "Prompt Caching / KV Reuse",
                    "value": prompt_caching,
                    "formatted": prompt_caching,
                    "source": "configured",
                    "tooltip": "Reuses previously processed prompt tokens between requests, reducing repeated prompt computation and improving time to first token.",
                },
                {
                    "key": "kv_offload",
                    "label": "KV Offloading",
                    "value": kv_offload,
                    "formatted": kv_offload,
                    "source": "configured"
                    if env.get("LLAMA_ARG_KV_OFFLOAD")
                    else "default",
                    "tooltip": "Controls whether KV cache is offloaded to host system RAM.",
                },
                {
                    "key": "kv_unified",
                    "label": "KV Unified Pool",
                    "value": kv_unified,
                    "formatted": kv_unified,
                    "source": "configured"
                    if env.get("LLAMA_ARG_KV_UNIFIED")
                    else "default",
                    "tooltip": "Shares a unified KV cache pool across concurrent slots to improve memory efficiency.",
                },
                {
                    "key": "cache_ram",
                    "label": "Cache RAM Limit",
                    "value": cache_ram,
                    "formatted": f"{cache_ram} MiB"
                    if cache_ram
                    else "Unlimited / Dynamic",
                    "source": "configured" if cache_ram else "default",
                    "tooltip": "Maximum host RAM limit allocated for prompt caching and offloaded KV state in MiB.",
                },
            ]
        )
    else:
        prefix_caching_flag = env.get("ENABLE_PREFIX_CACHING") or inference.get(
            "prefix_caching"
        )
        prefix_caching = (
            "Enabled"
            if str(prefix_caching_flag).lower() in ("1", "true", "enabled")
            else "Disabled"
        )
        chunked_prefill_flag = (
            env.get("ENABLE_CHUNKED_PREFILL")
            or env.get("VLLM_ENABLE_CHUNKED_PREFILL")
            or inference.get("chunked_prefill")
        )
        chunked_prefill = (
            "Enabled"
            if str(chunked_prefill_flag).lower() in ("1", "true", "enabled")
            else "Disabled"
        )
        eager_flag = env.get("ENFORCE_EAGER")
        compilation_mode = (
            "Eager Execution (Graphs Disabled)"
            if eager_flag in ("1", "true", "True")
            else "ROCm / CUDA Graph Enabled"
        )
        attention_items.extend(
            [
                {
                    "key": "prefix_caching",
                    "label": "Prefix Caching",
                    "value": prefix_caching,
                    "formatted": prefix_caching,
                    "source": "configured"
                    if env.get("ENABLE_PREFIX_CACHING")
                    else "runtime",
                    "tooltip": "Reuses KV-cache entries for requests that share the same prompt prefix, reducing repeated computation.",
                },
                {
                    "key": "chunked_prefill",
                    "label": "Chunked Prefill",
                    "value": chunked_prefill,
                    "formatted": chunked_prefill,
                    "source": "configured"
                    if (
                        env.get("ENABLE_CHUNKED_PREFILL")
                        or env.get("VLLM_ENABLE_CHUNKED_PREFILL")
                    )
                    else "runtime",
                    "tooltip": "Processes large prompts in smaller pieces so long prompt ingestion can coexist more efficiently with token generation.",
                },
                {
                    "key": "compilation_mode",
                    "label": "Graph Compilation Mode",
                    "value": compilation_mode,
                    "formatted": compilation_mode,
                    "source": "configured" if eager_flag else "default",
                    "tooltip": "Runtime optimization that reduces execution overhead by reusing compiled or captured execution paths.",
                },
            ]
        )

    # 5. SPECULATIVE DECODING
    spec_type = (
        env.get("LLAMA_ARG_SPECULATIVE")
        or ("draft-mtp" if env.get("LLAMA_ARG_DRAFT_MAX") else None)
        if backend_type == "llama_cpp"
        else env.get("SPECULATIVE_MODEL")
    )
    spec_depth = (
        env.get("LLAMA_ARG_DRAFT_MAX")
        if backend_type == "llama_cpp"
        else env.get("NUM_SPECULATIVE_TOKENS")
    )
    spec_accept = inference.get("speculative_acceptance_rate")
    speculative_items = [
        {
            "key": "speculative_status",
            "label": "Speculative Decoding",
            "value": "Enabled"
            if (spec_type or spec_depth)
            else "Disabled / Not configured",
            "formatted": "Enabled"
            if (spec_type or spec_depth)
            else "Disabled / Not configured",
            "source": "configured" if (spec_type or spec_depth) else "default",
            "tooltip": "Speculative decoding predicts several tokens ahead and verifies them together, potentially increasing generation speed.",
        },
        {
            "key": "speculative_type",
            "label": "Speculative Type",
            "value": spec_type,
            "formatted": str(spec_type) if spec_type else "None",
            "source": "configured" if spec_type else "default",
            "tooltip": "Method used to generate speculative tokens before the main model verifies them.",
        },
        {
            "key": "draft_depth",
            "label": "MTP / Draft Depth",
            "value": spec_depth,
            "formatted": f"{spec_depth} tokens" if spec_depth else "Unavailable",
            "source": "configured" if spec_depth else "unavailable",
            "tooltip": "Maximum number of speculative tokens generated ahead. Higher values can improve speed if predictions are accepted, but may waste work when predictions are rejected.",
        },
        {
            "key": "speculative_acceptance_rate",
            "label": "Speculative Acceptance Rate",
            "value": spec_accept,
            "formatted": f"{spec_accept:.1f}%"
            if spec_accept is not None
            else "Unavailable",
            "source": "runtime" if spec_accept is not None else "unavailable",
            "tooltip": "Percentage of speculative tokens accepted by the main model. Higher acceptance usually means speculative decoding is providing more benefit.",
        },
    ]

    # 6. SAMPLING
    temp = generation.get("temperature") or env.get("LLAMA_ARG_TEMP")
    top_k = generation.get("top_k") or env.get("LLAMA_ARG_TOP_K")
    top_p = generation.get("top_p") or env.get("LLAMA_ARG_TOP_P")
    min_p = generation.get("min_p") or env.get("LLAMA_ARG_MIN_P")
    repeat_penalty = generation.get("repeat_penalty") or env.get(
        "LLAMA_ARG_REPEAT_PENALTY"
    )
    sampling_items = [
        {
            "key": "temperature",
            "label": "Temperature",
            "value": temp,
            "formatted": f"{float(temp):.2f}" if temp is not None else "Unavailable",
            "source": "runtime"
            if generation.get("temperature") is not None
            else ("configured" if env.get("LLAMA_ARG_TEMP") else "unavailable"),
            "tooltip": "Controls randomness. Lower values make responses more deterministic and are often preferred for coding.",
        },
        {
            "key": "top_k",
            "label": "Top K",
            "value": top_k,
            "formatted": str(top_k) if top_k is not None else "Unavailable",
            "source": "runtime"
            if generation.get("top_k") is not None
            else ("configured" if env.get("LLAMA_ARG_TOP_K") else "unavailable"),
            "tooltip": "Limits token selection to the K most likely choices. Lower values make output more focused.",
        },
        {
            "key": "top_p",
            "label": "Top P",
            "value": top_p,
            "formatted": f"{float(top_p):.2f}" if top_p is not None else "Unavailable",
            "source": "runtime"
            if generation.get("top_p") is not None
            else ("configured" if env.get("LLAMA_ARG_TOP_P") else "unavailable"),
            "tooltip": "Limits token selection to the smallest group whose combined probability reaches this value.",
        },
        {
            "key": "min_p",
            "label": "Min P",
            "value": min_p,
            "formatted": f"{float(min_p):.2f}" if min_p is not None else "Unavailable",
            "source": "runtime"
            if generation.get("min_p") is not None
            else ("configured" if env.get("LLAMA_ARG_MIN_P") else "unavailable"),
            "tooltip": "Removes very unlikely token choices relative to the most probable token, helping reduce low-quality output.",
        },
        {
            "key": "repeat_penalty",
            "label": "Repeat Penalty",
            "value": repeat_penalty,
            "formatted": f"{float(repeat_penalty):.2f}"
            if repeat_penalty is not None
            else "Unavailable",
            "source": "runtime"
            if generation.get("repeat_penalty") is not None
            else (
                "configured" if env.get("LLAMA_ARG_REPEAT_PENALTY") else "unavailable"
            ),
            "tooltip": "Penalizes recently used tokens to reduce unwanted repetition. Values near 1 apply little or no penalty.",
        },
    ]

    # 7. GPU & HARDWARE
    gpu_util = gpu.get("gpu_utilization")
    mem_util = gpu.get("memory_utilization")
    clock = gpu.get("core_clock")
    mem_clock = gpu.get("memory_clock")
    power_draw = gpu.get("power_draw")
    power_limit = gpu.get("power_limit")
    temp_c = gpu.get("temperature")
    driver = gpu.get("driver_version") or "Unknown"
    rocm_ver = gpu.get("compute_runtime_version") or "ROCm"
    gpu_power_str = (
        f"{power_draw:.0f} W" + (f" / {power_limit:.0f} W" if power_limit else "")
        if power_draw is not None
        else "Unavailable"
    )
    gpu_items = [
        {
            "key": "gpu_utilization",
            "label": "GPU Utilization",
            "value": gpu_util,
            "formatted": f"{gpu_util:.0f}%" if gpu_util is not None else "Unavailable",
            "source": "measured",
            "tooltip": "Percentage of GPU compute capacity currently being used.",
        },
        {
            "key": "memory_controller_utilization",
            "label": "Memory Controller Utilization",
            "value": mem_util,
            "formatted": f"{mem_util:.0f}%" if mem_util is not None else "Unavailable",
            "source": "measured",
            "tooltip": "Indicates how heavily GPU memory bandwidth is being used. LLM token generation is often memory-bandwidth limited.",
        },
        {
            "key": "gpu_clock",
            "label": "GPU Clock",
            "value": clock,
            "formatted": f"{clock:.0f} MHz" if clock is not None else "Unavailable",
            "source": "measured",
            "tooltip": "Current GPU operating frequency. Reduced clocks can indicate power, thermal, or utilization limits.",
        },
        {
            "key": "memory_clock",
            "label": "GPU Memory Clock",
            "value": mem_clock,
            "formatted": f"{mem_clock:.0f} MHz"
            if mem_clock is not None
            else "Unavailable",
            "source": "measured",
            "tooltip": "Current GPU memory operating frequency.",
        },
        {
            "key": "gpu_power",
            "label": "GPU Power",
            "value": power_draw,
            "formatted": gpu_power_str,
            "source": "measured",
            "tooltip": "Current GPU power consumption. Low power during inference can indicate that the GPU is not being fully utilized.",
        },
        {
            "key": "gpu_temperature",
            "label": "GPU Temperature",
            "value": temp_c,
            "formatted": f"{temp_c:.0f} °C" if temp_c is not None else "Unavailable",
            "source": "measured",
            "tooltip": "Current GPU temperature. High temperatures may cause clock throttling and lower inference performance.",
        },
        {
            "key": "compute_driver",
            "label": "Compute Runtime / Driver",
            "value": f"{rocm_ver} · driver {driver}",
            "formatted": f"{rocm_ver} · driver {driver}",
            "source": "measured",
            "tooltip": "Host compute runtime and graphics driver version reported by the GPU telemetry provider.",
        },
    ]

    # 8. PERFORMANCE
    prompt_tps = inference.get("prompt_tokens_per_second")
    out_tps = inference.get("output_tokens_per_second")
    perf_items = [
        {
            "key": "ttft",
            "label": "TTFT (Time to First Token)",
            "value": inference.get("ttft_seconds"),
            "formatted": f"{inference['ttft_seconds']*1000:.0f} ms"
            if inference.get("ttft_seconds")
            else "Unavailable (Run test)",
            "source": "benchmark" if inference.get("ttft_seconds") else "unavailable",
            "tooltip": "Time from submitting the request until the first generated token is returned. Prompt processing and cache reuse strongly affect this value.",
        },
        {
            "key": "prompt_throughput",
            "label": "Prompt Throughput",
            "value": prompt_tps,
            "formatted": f"{prompt_tps:.1f} tok/s"
            if (prompt_tps and prompt_tps > 0)
            else "Idle (0 tok/s)",
            "source": "runtime" if prompt_tps is not None else "unavailable",
            "tooltip": "Rate at which input prompt tokens are processed before generation begins.",
        },
        {
            "key": "output_throughput",
            "label": "Output Throughput",
            "value": out_tps,
            "formatted": f"{out_tps:.1f} tok/s"
            if (out_tps and out_tps > 0)
            else "Idle (0 tok/s)",
            "source": "runtime" if out_tps is not None else "unavailable",
            "tooltip": "Rate at which new response tokens are generated.",
        },
        {
            "key": "e2e_latency",
            "label": "End-to-End Latency",
            "value": inference.get("e2e_seconds"),
            "formatted": f"{inference['e2e_seconds']:.2f} s"
            if inference.get("e2e_seconds")
            else "Unavailable (Run test)",
            "source": "benchmark" if inference.get("e2e_seconds") else "unavailable",
            "tooltip": "Total request duration including prompt processing and token generation.",
        },
    ]

    return {
        "engine": backend_name,
        "engine_type": backend_type,
        "groups": [
            {"id": "model", "title": "MODEL", "items": model_items},
            {
                "id": "context_memory",
                "title": "CONTEXT & MEMORY",
                "items": context_items,
            },
            {
                "id": "scheduling",
                "title": "SCHEDULING & CONCURRENCY",
                "items": scheduling_items,
            },
            {
                "id": "attention_cache",
                "title": "ATTENTION & CACHE",
                "items": attention_items,
            },
            {
                "id": "speculative_decoding",
                "title": "SPECULATIVE DECODING",
                "items": speculative_items,
            },
            {"id": "sampling", "title": "SAMPLING", "items": sampling_items},
            {"id": "gpu_hardware", "title": "GPU & HARDWARE", "items": gpu_items},
            {"id": "performance", "title": "PERFORMANCE", "items": perf_items},
        ],
    }


class CapabilityDiscoveryService:
    """Compose normalized host, GPU, Docker, endpoint, and log evidence."""

    def __init__(self, runner: CommandRunner = run_read_only) -> None:
        self.runner = runner

    def discover(self) -> dict[str, Any]:
        backend = inference_backend()
        docker = DockerVLLMDiscovery(self.runner, backend).discover()
        gpu_provider = self._gpu_provider()
        gpus = [gpu.to_dict() for gpu in gpu_provider.get_gpu_devices()]
        endpoint_provider = (
            LlamaCppEndpointDiscovery(inference_base_url())
            if backend == "llama_cpp"
            else VLLMEndpointDiscovery(inference_base_url())
        )
        endpoint = endpoint_provider.discover()
        logs = ""
        if docker.get("container"):
            try:
                completed = self.runner(
                    ["docker", "logs", "--tail", "2000", docker["container"]]
                )
                logs = completed.stdout + completed.stderr
            except (OSError, subprocess.SubprocessError):
                pass
        log_telemetry = (
            VLLMLogTelemetryParser.parse(logs)
            if backend == "vllm"
            else {
                "memory_source": "Unavailable",
                "runtime_activation_memory_gib": None,
                "backend_non_torch_memory_gib": None,
            }
        )
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
        inference_snapshot = {**endpoint, **log_telemetry}
        memory_snapshot = {
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
        }
        configuration = build_normalized_configuration(
            backend_type=backend,
            inference=inference_snapshot,
            docker=docker,
            gpus=gpus,
            memory=memory_snapshot,
        )
        return {
            "backend": {
                "type": backend,
                "name": backend_display_name(backend),
                "base_url": inference_base_url(),
            },
            "host": HostDiscovery().discover(),
            "gpus": gpus,
            "runtime": docker,
            "vllm": inference_snapshot,
            "inference": inference_snapshot,
            "configuration": configuration,
            "inference_configuration": configuration,
            "memory": memory_snapshot,
            "lifecycle_preview": DockerVLLMDiscovery.lifecycle_preview(docker),
        }

    @staticmethod
    def _gpu_provider() -> AMDGPUProvider | NVGPUProvider | GenericGPUProvider:
        if shutil.which("amd-smi") or shutil.which("rocm-smi"):
            return AMDGPUProvider()
        if shutil.which("nvidia-smi"):
            return NVGPUProvider()
        return GenericGPUProvider()
