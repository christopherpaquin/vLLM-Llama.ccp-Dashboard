"""Tests for normalized GPU providers."""

import json
import subprocess

from core.gpu_telemetry import AMDGPUProvider


def completed(command: list[str], payload: object) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")


def test_amd_smi_is_preferred_and_normalized() -> None:
    static = {
        "gpu_data": [
            {
                "gpu": 0,
                "asic": {"market_name": "AMD Test", "asic_serial": "abc"},
                "driver": {"version": "driver"},
                "limit": {"ppt0": {"socket_power_limit": {"value": 300, "unit": "W"}}},
            }
        ]
    }
    metric = {
        "gpu_data": [
            {
                "gpu": 0,
                "usage": {"gfx_activity": {"value": 12}, "umc_activity": {"value": 3}},
                "mem_usage": {
                    "total_vram": {"value": 32000, "unit": "MB"},
                    "used_vram": {"value": 24000, "unit": "MB"},
                    "free_vram": {"value": 8000, "unit": "MB"},
                },
                "temperature": {"edge": {"value": 45}},
                "power": {"socket_power": {"value": 80}},
                "clock": {
                    "gfx_0": {"clk": {"value": 1000}},
                    "mem_0": {"clk": {"value": 900}},
                },
            }
        ]
    }
    processes = [
        {
            "gpu": 0,
            "process_list": [
                {
                    "process_info": {
                        "pid": 42,
                        "name": "vllm",
                        "memory_usage": {"vram_mem": {"value": 1234}},
                    }
                }
            ],
        }
    ]

    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        if command[1] == "static":
            return completed(command, static)
        if command[1] == "metric":
            return completed(command, metric)
        if command[1] == "process":
            return completed(command, processes)
        return subprocess.CompletedProcess(command, 0, "ROCm version: 7.2.2 |", "")

    provider = AMDGPUProvider(runner, which=lambda name: f"/usr/bin/{name}")
    gpu = provider.get_gpu_devices()[0]

    assert gpu.telemetry_provider == "amd-smi"
    assert gpu.model == "AMD Test"
    assert gpu.vram_free == 8000 * 1024**2
    assert gpu.power_draw == 80
    assert gpu.processes[0]["vram_bytes"] == 1234
    assert gpu.compute_runtime_version == "7.2.2"


def test_rocm_smi_is_used_when_amd_smi_is_absent() -> None:
    payload = {
        "card0": {
            "Unique ID": "gpu0",
            "Card Series": "Fallback GPU",
            "VRAM Total Memory (B)": "1000",
            "VRAM Total Used Memory (B)": "250",
            "GPU use (%)": "5",
        },
        "system": {"Driver version": "test"},
    }
    provider = AMDGPUProvider(
        lambda command: completed(command, payload),
        which=lambda name: "/usr/bin/rocm-smi" if name == "rocm-smi" else None,
    )

    gpu = provider.get_gpu_devices()[0]

    assert gpu.telemetry_provider == "rocm-smi"
    assert gpu.vram_free == 750
    assert gpu.temperature is None
