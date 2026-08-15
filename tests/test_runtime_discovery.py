"""Tests for host, Docker, endpoint, and startup-log discovery."""

import json
import subprocess
from pathlib import Path

from core.runtime_discovery import (
    DockerVLLMDiscovery,
    HostDiscovery,
    LlamaCppEndpointDiscovery,
    VLLMEndpointDiscovery,
    VLLMLogTelemetryParser,
)


def test_host_discovery_reads_linux_release(tmp_path: Path, monkeypatch) -> None:
    release = tmp_path / "os-release"
    cpuinfo = tmp_path / "cpuinfo"
    release.write_text('ID="ubuntu"\nNAME="Ubuntu"\nVERSION_ID="24.04"\n')
    cpuinfo.write_text("model name : Intel(R) Core(TM) i7-8086K CPU @ 4.00GHz\n")
    monkeypatch.setenv("VLLM_HOSTNAME", "configured-host")
    monkeypatch.setenv("HOST_PRIMARY_IP", "192.0.2.10")

    result = HostDiscovery(release, cpuinfo).discover()

    assert result["os_id"] == "ubuntu"
    assert result["os_version"] == "24.04"
    assert result["memory_total_bytes"] > 0
    assert result["cpu_model"] == "Intel(R) Core(TM) i7-8086K CPU @ 4.00GHz"
    assert result["cpu_model_short"] == "Intel Core i7-8086K"
    assert result["hostname"] == "configured-host"
    assert result["primary_ip"] == "192.0.2.10"


def test_cpu_short_name_handles_amd_core_suffix() -> None:
    assert (
        HostDiscovery._short_cpu_model("AMD Ryzen 9 9950X 16-Core Processor")
        == "AMD Ryzen 9 9950X"
    )


def test_docker_compose_discovery_and_safe_preview() -> None:
    ps = {"Names": "vllm", "Image": "rocm/vllm:1"}
    inspect = [
        {
            "Id": "abc",
            "Config": {
                "Image": "rocm/vllm:1",
                "Env": [
                    "MODEL_ID=owner/model",
                    "DTYPE=float16",
                    "SECRET=hidden",
                    "HF_HOME=/cache",
                ],
                "Labels": {
                    "com.docker.compose.project.config_files": "/srv/vllm/compose.yaml",
                    "com.docker.compose.project": "vllm",
                    "com.docker.compose.service": "vllm",
                },
            },
            "State": {"Running": True, "Pid": 42, "Health": {"Status": "healthy"}},
            "Mounts": [{"Source": "/models", "Destination": "/cache"}],
        }
    ]

    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["docker", "ps"]:
            return subprocess.CompletedProcess(command, 0, json.dumps(ps), "")
        if command[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(command, 0, json.dumps(inspect), "")
        if command[:2] == ["docker", "top"]:
            return subprocess.CompletedProcess(
                command, 0, "PID COMMAND\n42 vllm\n84 python\n", ""
            )
        return subprocess.CompletedProcess(command, 0, "27.0.0\n", "")

    result = DockerVLLMDiscovery(runner).discover()
    preview = DockerVLLMDiscovery.lifecycle_preview(result)

    assert result["lifecycle_mechanism"] == "docker-compose"
    assert result["model_cache_location"] == "/models"
    assert result["host_pid"] == 42
    assert result["container_pids"] == [42, 84]
    assert "SECRET" not in result["environment"]
    assert result["environment"]["DTYPE"] == "float16"
    assert preview["enabled"] is False
    assert preview["actions"]["restart"] == [
        "docker",
        "compose",
        "-f",
        "/srv/vllm/compose.yaml",
        "restart",
        "vllm",
    ]


def test_docker_discovery_ignores_management_portal_name_collision() -> None:
    containers = [
        {"Names": "vllm-management-portal", "Image": "vllm-management-portal:0.1.0"},
        {"Names": "vllm", "Image": "rocm/vllm:rocm7.14.0"},
    ]

    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["docker", "ps"]:
            output = "\n".join(json.dumps(item) for item in containers)
            return subprocess.CompletedProcess(command, 0, output, "")
        if command[:2] == ["docker", "inspect"]:
            inspected = [{"Config": {"Image": "rocm/vllm:rocm7.14.0"}, "State": {}}]
            return subprocess.CompletedProcess(command, 0, json.dumps(inspected), "")
        return subprocess.CompletedProcess(command, 0, "", "")

    assert DockerVLLMDiscovery(runner).discover()["container"] == "vllm"


def test_docker_discovers_llama_cpp_container() -> None:
    containers = [
        {
            "Names": "vllm-llama-cpp-dashboard-docker-proxy",
            "Image": "tecnativa/docker-socket-proxy:v0.4.2",
            "Labels": "com.docker.compose.project=vllm-management-portal",
        },
        {"Names": "llamacpp", "Image": "local-image-id"},
    ]

    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["docker", "ps"]:
            return subprocess.CompletedProcess(
                command, 0, "\n".join(json.dumps(item) for item in containers), ""
            )
        if command[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(
                command,
                0,
                json.dumps(
                    [
                        {
                            "Config": {
                                "Image": "ghcr.io/ggml-org/llama.cpp:server",
                                "Env": [
                                    "LLAMA_ARG_MODEL=/models/coder.gguf",
                                    "LLAMA_ARG_N_GPU_LAYERS=99",
                                    "LLAMA_ARG_UBATCH=1024",
                                    "SECRET=hidden",
                                ],
                                "Labels": {
                                    "org.opencontainers.image.version": "b10438"
                                },
                            },
                            "State": {},
                            "Mounts": [
                                {"Source": "/srv/models", "Destination": "/models"}
                            ],
                        }
                    ]
                ),
                "",
            )
        return subprocess.CompletedProcess(command, 0, "", "")

    result = DockerVLLMDiscovery(runner, "llama_cpp").discover()

    assert result["container"] == "llamacpp"
    assert result["image"] == "ghcr.io/ggml-org/llama.cpp:server"
    assert result["backend_version"] == "b10438"
    assert result["model_cache_location"] == "/srv/models"
    assert result["environment"] == {
        "LLAMA_ARG_MODEL": "/models/coder.gguf",
        "LLAMA_ARG_N_GPU_LAYERS": "99",
        "LLAMA_ARG_UBATCH": "1024",
    }


def test_llama_cpp_endpoint_discovery_uses_official_read_only_apis(monkeypatch) -> None:
    responses = {
        "/health": (True, {"status": "ok"}),
        "/v1/models": (
            True,
            {
                "data": [
                    {
                        "id": "coder-q4.gguf",
                        "meta": {"n_ctx_train": 32768, "n_params": 7, "size": 4},
                    }
                ]
            },
        ),
        "/props": (
            True,
            {
                "default_generation_settings": {
                    "n_ctx": 8192,
                    "params": {"temperature": 0.8, "top_k": 40},
                },
                "model_ftype": "Q4_K - Medium",
                "total_slots": 4,
                "build_info": "b10438-abcdef",
            },
        ),
    }
    monkeypatch.setattr(
        "core.runtime_discovery.read_json",
        lambda url: responses[next(path for path in responses if url.endswith(path))],
    )
    monkeypatch.setattr(
        "core.runtime_discovery.read_text",
        lambda url: (
            True,
            "llamacpp:prompt_tokens_seconds 120\nllamacpp:predicted_tokens_seconds 48\n",
        ),
    )

    result = LlamaCppEndpointDiscovery("http://llama:8080").discover()

    assert result["api_healthy"] is True
    assert result["backend_name"] == "llama.cpp"
    assert result["active_model"] == "coder-q4.gguf"
    assert result["configured_max_model_len"] == 8192
    assert result["native_context_tokens"] == 32768
    assert result["model_quantization"] == "Q4_K - Medium"
    assert result["maximum_concurrency"] == 4
    assert result["backend_version"] == "b10438-abcdef"
    assert result["prompt_tokens_per_second"] == 120
    assert result["output_tokens_per_second"] == 48
    assert result["generation_settings"]["temperature"] == 0.8
    assert result["kv_cache_utilization_percent"] is None


def test_metrics_and_startup_logs_are_parsed_without_estimates() -> None:
    metrics = 'vllm:kv_cache_usage_perc{engine="0"} 0.25\n'
    assert VLLMEndpointDiscovery._metric(metrics, "vllm:kv_cache_usage_perc", 100) == 25

    parsed = VLLMLogTelemetryParser.parse(
        "Using max model len 32,768\n"
        "V1 LLM engine (v0.23.1)\n"
        "Model loading took 15.74 GiB memory\n"
        "Available KV cache memory: 4.61 GiB\n"
        "GPU KV cache size: 50,336 tokens\n"
        "Maximum concurrency for 32,768 tokens per request: 1.54x\n"
    )

    assert parsed["model_weight_memory_gib"] == 15.74
    assert parsed["kv_cache_capacity_tokens"] == 50336
    assert parsed["runtime_activation_memory_gib"] is None
    assert parsed["memory_source"] == "Reported by vLLM"
