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
        "/slots": (
            True,
            [
                {
                    "id": 0,
                    "n_ctx": 8192,
                    "is_processing": False,
                    "n_prompt_tokens_cache": 0,
                },
                {
                    "id": 1,
                    "n_ctx": 8192,
                    "is_processing": False,
                    "n_prompt_tokens_cache": 0,
                },
                {
                    "id": 2,
                    "n_ctx": 8192,
                    "is_processing": False,
                    "n_prompt_tokens_cache": 0,
                },
                {
                    "id": 3,
                    "n_ctx": 8192,
                    "is_processing": False,
                    "n_prompt_tokens_cache": 0,
                },
            ],
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
    assert result["kv_cache_capacity_tokens"] == 32768
    assert result["kv_cache_utilization_percent"] == 0.0
    assert result["prompt_tokens_per_second"] == 120
    assert result["output_tokens_per_second"] == 48
    assert result["generation_settings"]["temperature"] == 0.8


def test_llama_cpp_kv_cache_telemetry_sources(monkeypatch) -> None:
    # 1. Prometheus metric ratio priority
    responses = {
        "/health": (True, {"status": "ok"}),
        "/v1/models": (True, {"data": [{"id": "model.gguf"}]}),
        "/props": (
            True,
            {"default_generation_settings": {"n_ctx": 4096}, "total_slots": 2},
        ),
        "/slots": (True, [{"id": 0, "n_ctx": 4096, "is_processing": False}]),
    }
    monkeypatch.setattr(
        "core.runtime_discovery.read_json",
        lambda url: responses[next(path for path in responses if url.endswith(path))],
    )
    monkeypatch.setattr(
        "core.runtime_discovery.read_text",
        lambda url: (True, "llamacpp:kv_cache_usage_ratio 0.355\n"),
    )
    result = LlamaCppEndpointDiscovery("http://llama:8080").discover()
    assert result["kv_cache_capacity_tokens"] == 4096
    assert result["kv_cache_utilization_percent"] == 35.5

    # 2. Live slot activity calculation when Prometheus ratio metric is absent
    responses["/slots"] = (
        True,
        [
            {"id": 0, "n_ctx": 4096, "is_processing": True, "n_prompt_tokens": 1024},
            {
                "id": 1,
                "n_ctx": 4096,
                "is_processing": False,
                "n_prompt_tokens_cache": 512,
            },
        ],
    )
    monkeypatch.setattr(
        "core.runtime_discovery.read_text",
        lambda url: (True, "llamacpp:prompt_tokens_seconds 50\n"),
    )
    result = LlamaCppEndpointDiscovery("http://llama:8080").discover()
    assert result["kv_cache_capacity_tokens"] == 8192
    assert result["kv_cache_utilization_percent"] == 18.75  # (1024 + 512) / 8192 * 100

    # 3. Unavailable endpoints fallback without fabrication
    responses["/slots"] = (False, None)
    monkeypatch.setattr(
        "core.runtime_discovery.read_text",
        lambda url: (False, None),
    )
    result = LlamaCppEndpointDiscovery("http://llama:8080").discover()
    assert result["kv_cache_capacity_tokens"] == 8192  # 4096 * 2 from props
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


def test_build_normalized_configuration_llama_cpp() -> None:
    from core.runtime_discovery import build_normalized_configuration

    inference = {
        "active_model": "Qwen3.8-27B-Q4_K_M.gguf",
        "served_model_name": "qwen3.8-27b",
        "configured_max_model_len": 65536,
        "native_context_tokens": 262144,
        "model_size_bytes": 17072521216,
        "model_quantization": "Q4_K - Medium",
        "maximum_concurrency": 1,
        "kv_cache_capacity_tokens": 65536,
        "kv_cache_utilization_percent": 0.0,
        "prompt_tokens_per_second": 0.0,
        "output_tokens_per_second": 0.0,
        "generation_settings": {
            "temperature": 0.8,
            "top_k": 40,
            "top_p": 0.95,
            "min_p": 0.05,
            "repeat_penalty": 1.1,
        },
    }
    docker = {
        "environment": {
            "LLAMA_ARG_MODEL": "/models/Qwen3.8-27B-Q4_K_M.gguf",
            "LLAMA_ARG_CTX_SIZE": "65536",
            "LLAMA_ARG_N_GPU_LAYERS": "99",
            "LLAMA_ARG_BATCH": "2048",
            "LLAMA_ARG_UBATCH": "512",
            "LLAMA_ARG_PARALLEL": "1",
            "LLAMA_ARG_FLASH_ATTN": "auto",
            "LLAMA_ARG_CACHE_TYPE_K": "q8_0",
            "LLAMA_ARG_CACHE_TYPE_V": "q8_0",
            "LLAMA_ARG_CACHE_PROMPT": "1",
        }
    }
    gpus = [
        {
            "vram_used": 20185088000,
            "vram_total": 34225520640,
            "gpu_utilization": 0.0,
            "memory_utilization": 5.0,
            "core_clock": 1950.0,
            "memory_clock": 900.0,
            "power_draw": 46.0,
            "power_limit": 300.0,
            "temperature": 41.0,
            "compute_runtime_version": "ROCm 7.2.2",
            "driver_version": "6.12.0",
        }
    ]
    memory = {
        "vllm_process_vram_bytes": 18000000000,
        "headroom_bytes": 14040432640,
    }

    config = build_normalized_configuration(
        "llama_cpp", inference, docker, gpus, memory
    )

    assert config["engine"] == "llama.cpp"
    assert config["engine_type"] == "llama_cpp"
    assert len(config["groups"]) == 8

    # All items must have tooltips and labels
    all_items = [item for group in config["groups"] for item in group["items"]]
    for item in all_items:
        assert item["label"], f"Missing label for {item}"
        assert item["tooltip"], f"Missing tooltip for {item['label']}"
        assert item["source"] in (
            "runtime",
            "configured",
            "measured",
            "default",
            "benchmark",
            "unavailable",
        )

    # Group titles check
    titles = [g["title"] for g in config["groups"]]
    assert "MODEL" in titles
    assert "CONTEXT & MEMORY" in titles
    assert "SCHEDULING & CONCURRENCY" in titles
    assert "ATTENTION & CACHE" in titles
    assert "SPECULATIVE DECODING" in titles
    assert "SAMPLING" in titles
    assert "GPU & HARDWARE" in titles
    assert "PERFORMANCE" in titles

    # Check llama.cpp specific values
    sched_items = next(g["items"] for g in config["groups"] if g["id"] == "scheduling")
    sched_keys = [item["key"] for item in sched_items]
    assert "gpu_layers" in sched_keys
    assert "parallel_slots" in sched_keys
    assert "batch_size" in sched_keys
    assert "ubatch_size" in sched_keys
    assert "max_num_seqs" not in sched_keys

    gpu_layers_item = next(item for item in sched_items if item["key"] == "gpu_layers")
    assert gpu_layers_item["formatted"] == "All layers GPU resident (99)"

    ctx_items = next(
        g["items"] for g in config["groups"] if g["id"] == "context_memory"
    )
    ctx_keys = [item["key"] for item in ctx_items]
    assert "kv_cache_type_k" in ctx_keys
    assert "kv_cache_type_v" in ctx_keys
    assert "gpu_memory_utilization" not in ctx_keys


def test_build_normalized_configuration_vllm() -> None:
    from core.runtime_discovery import build_normalized_configuration

    inference = {
        "active_model": "stelterlab/Qwen3-Coder-30B-A3B-Instruct-AWQ",
        "served_model_name": "qwen3-coder-30b-a3b",
        "configured_max_model_len": 32768,
        "model_weight_memory_gib": 15.74,
        "kv_cache_memory_gib": 4.61,
        "kv_cache_capacity_tokens": 50336,
        "kv_cache_utilization_percent": 12.5,
        "prompt_tokens_per_second": 1240.0,
        "output_tokens_per_second": 27.5,
        "ttft_seconds": 0.779,
        "e2e_seconds": 2.118,
    }
    docker = {
        "environment": {
            "MODEL_ID": "stelterlab/Qwen3-Coder-30B-A3B-Instruct-AWQ",
            "MAX_MODEL_LEN": "32768",
            "GPU_MEMORY_UTILIZATION": "0.68",
            "QUANTIZATION": "AWQ",
            "KV_CACHE_DTYPE": "auto",
            "MAX_NUM_SEQS": "8",
            "MAX_NUM_BATCHED_TOKENS": "8192",
            "ENABLE_PREFIX_CACHING": "1",
            "ENABLE_CHUNKED_PREFILL": "1",
            "TENSOR_PARALLEL_SIZE": "1",
        }
    }
    gpus = [
        {
            "vram_used": 32085088000,
            "vram_total": 34225520640,
            "gpu_utilization": 37.0,
            "memory_utilization": 42.0,
            "core_clock": 2100.0,
            "memory_clock": 900.0,
            "power_draw": 245.0,
            "power_limit": 300.0,
            "temperature": 48.0,
            "compute_runtime_version": "ROCm 7.14.0",
            "driver_version": "6.12.0",
        }
    ]
    memory = {
        "vllm_process_vram_bytes": 24360000000,
        "headroom_bytes": 2140432640,
    }

    config = build_normalized_configuration("vllm", inference, docker, gpus, memory)

    assert config["engine"] == "vLLM"
    assert config["engine_type"] == "vllm"

    # Check vLLM specific values
    sched_items = next(g["items"] for g in config["groups"] if g["id"] == "scheduling")
    sched_keys = [item["key"] for item in sched_items]
    assert "max_num_seqs" in sched_keys
    assert "max_num_batched_tokens" in sched_keys
    assert "tensor_parallel_size" in sched_keys
    assert "gpu_layers" not in sched_keys
    assert "parallel_slots" not in sched_keys

    ctx_items = next(
        g["items"] for g in config["groups"] if g["id"] == "context_memory"
    )
    ctx_keys = [item["key"] for item in ctx_items]
    assert "gpu_memory_utilization" in ctx_keys
    assert "kv_cache_dtype" in ctx_keys
    assert "kv_cache_size" in ctx_keys
    assert "kv_cache_type_k" not in ctx_keys

    attn_items = next(
        g["items"] for g in config["groups"] if g["id"] == "attention_cache"
    )
    attn_keys = [item["key"] for item in attn_items]
    assert "prefix_caching" in attn_keys
    assert "chunked_prefill" in attn_keys
    assert "compilation_mode" in attn_keys
    assert "kv_unified" not in attn_keys


def test_build_normalized_configuration_graceful_missing_metrics() -> None:
    from core.runtime_discovery import build_normalized_configuration

    config = build_normalized_configuration("llama_cpp", {}, {}, [], {})

    assert config["engine"] == "llama.cpp"
    for group in config["groups"]:
        for item in group["items"]:
            assert item["tooltip"], f"Missing tooltip for {item['label']}"
            # Unavailable items should format cleanly as Unavailable or Idle or Default
            assert item["formatted"] is not None
