"""Normalized GPU telemetry providers.

Unknown metrics are represented as ``None``. No provider substitutes zero for
missing hardware data.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from typing import Any

from .capabilities import GPUDetails, GPUProvider, GPUVendor


CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        check=True,
        text=True,
        timeout=10,
    )


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _metric(container: Any, *keys: str) -> float | None:
    current = container
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    if isinstance(current, dict):
        current = current.get("value")
    return _number(current)


def _memory_bytes(container: Any, *keys: str) -> float | None:
    current = container
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    if not isinstance(current, dict):
        return None
    value = _number(current.get("value"))
    unit = str(current.get("unit", "B")).upper()
    factors = {
        "B": 1,
        "KB": 1024,
        "MB": 1024**2,
        "MIB": 1024**2,
        "GB": 1024**3,
        "GIB": 1024**3,
    }
    return value * factors[unit] if value is not None and unit in factors else None


class AMDGPUProvider(GPUProvider):
    """AMD SMI telemetry with ROCm SMI fallback."""

    def __init__(
        self,
        command_runner: CommandRunner = _run,
        which: Callable[[str], str | None] = shutil.which,
    ) -> None:
        self._run = command_runner
        self._which = which

    def get_gpu_devices(self) -> list[GPUDetails]:
        if self._which("amd-smi"):
            try:
                return self._read_amd_smi()
            except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
                pass
        if self._which("rocm-smi"):
            try:
                return self._read_rocm_smi()
            except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
                pass
        return []

    def _read_amd_smi(self) -> list[GPUDetails]:
        static = json.loads(
            self._run(["amd-smi", "static", "--gpu", "all", "--json"]).stdout
        )
        metric = json.loads(
            self._run(["amd-smi", "metric", "--gpu", "all", "--json"]).stdout
        )
        try:
            process = json.loads(
                self._run(["amd-smi", "process", "--gpu", "all", "--json"]).stdout
            )
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
            process = []

        static_by_id = {item.get("gpu"): item for item in static.get("gpu_data", [])}
        process_by_id = {
            item.get("gpu"): item for item in process if isinstance(item, dict)
        }
        devices: list[GPUDetails] = []
        for item in metric.get("gpu_data", []):
            gpu_id = item.get("gpu")
            details = static_by_id.get(gpu_id, {})
            asic = details.get("asic", {})
            vram_total = _memory_bytes(item, "mem_usage", "total_vram")
            vram_used = _memory_bytes(item, "mem_usage", "used_vram")
            vram_free = _memory_bytes(item, "mem_usage", "free_vram")
            devices.append(
                GPUDetails(
                    device_index=int(gpu_id),
                    uuid=str(
                        asic.get("asic_serial")
                        or details.get("bus", {}).get("bdf")
                        or "unknown"
                    ),
                    vendor=GPUVendor.AMD,
                    model=str(asic.get("market_name") or "Unknown AMD GPU"),
                    vram_total=vram_total,
                    vram_used=vram_used,
                    vram_free=vram_free,
                    gpu_utilization=_metric(item, "usage", "gfx_activity"),
                    memory_utilization=_metric(item, "usage", "umc_activity"),
                    temperature=_metric(item, "temperature", "edge"),
                    power_draw=_metric(item, "power", "socket_power"),
                    power_limit=_metric(details, "limit", "ppt0", "socket_power_limit"),
                    core_clock=_metric(item, "clock", "gfx_0", "clk"),
                    memory_clock=_metric(item, "clock", "mem_0", "clk"),
                    driver_version=str(
                        details.get("driver", {}).get("version") or "Unknown"
                    ),
                    compute_runtime_version=self._runtime_version(),
                    processes=self._parse_amd_processes(process_by_id.get(gpu_id, {})),
                    telemetry_provider="amd-smi",
                )
            )
        return devices

    @staticmethod
    def _parse_amd_processes(data: dict[str, Any]) -> list[dict[str, Any]]:
        parsed = []
        for entry in data.get("process_list", []):
            info = entry.get("process_info", {})
            parsed.append(
                {
                    "pid": info.get("pid"),
                    "name": None if info.get("name") == "N/A" else info.get("name"),
                    "vram_bytes": _metric(info, "memory_usage", "vram_mem"),
                }
            )
        return parsed

    def _runtime_version(self) -> str:
        try:
            output = self._run(["amd-smi", "version"]).stdout
        except (OSError, subprocess.SubprocessError):
            return "Unknown"
        marker = "ROCm version:"
        return (
            output.split(marker, 1)[1].split("|", 1)[0].strip()
            if marker in output
            else "Unknown"
        )

    def _read_rocm_smi(self) -> list[GPUDetails]:
        data = json.loads(
            self._run(
                [
                    "rocm-smi",
                    "--showdriverversion",
                    "--showproductname",
                    "--showmeminfo",
                    "vram",
                    "--showuse",
                    "--showtemp",
                    "--showpower",
                    "--showclocks",
                    "--showuniqueid",
                    "--json",
                ]
            ).stdout
        )
        devices = []
        for index, (card, item) in enumerate(
            (k, v) for k, v in data.items() if k.startswith("card")
        ):
            total = _number_from_text(item.get("VRAM Total Memory (B)"))
            used = _number_from_text(item.get("VRAM Total Used Memory (B)"))
            devices.append(
                GPUDetails(
                    index,
                    str(item.get("Unique ID") or card),
                    GPUVendor.AMD,
                    str(item.get("Card Series") or "Unknown AMD GPU"),
                    total,
                    used,
                    total - used if total is not None and used is not None else None,
                    _number_from_text(item.get("GPU use (%)")),
                    None,
                    _number_from_text(item.get("Temperature (Sensor edge) (C)")),
                    _number_from_text(item.get("Average Graphics Package Power (W)")),
                    None,
                    None,
                    None,
                    str(data.get("system", {}).get("Driver version") or "Unknown"),
                    "Unknown",
                    [],
                    "rocm-smi",
                )
            )
        return devices

    def _device(self, device_index: int) -> GPUDetails | None:
        return next(
            (gpu for gpu in self.get_gpu_devices() if gpu.device_index == device_index),
            None,
        )

    def get_gpu_utilization(self, device_index: int) -> float | None:
        device = self._device(device_index)
        return device.gpu_utilization if device else None

    def get_gpu_temperature(self, device_index: int) -> float | None:
        device = self._device(device_index)
        return device.temperature if device else None

    def get_gpu_power(self, device_index: int) -> dict[str, float | None]:
        device = self._device(device_index)
        return {
            "draw": device.power_draw if device else None,
            "limit": device.power_limit if device else None,
        }


def _number_from_text(value: Any) -> float | None:
    try:
        return float(str(value).strip().split()[0])
    except (TypeError, ValueError, IndexError):
        return None


def _mib_from_text(value: Any) -> float | None:
    number = _number_from_text(value)
    return number * 1024**2 if number is not None else None


class NVGPUProvider(GPUProvider):
    """NVIDIA SMI fallback provider; NVML support remains future work."""

    QUERY = (
        "index,uuid,name,memory.total,memory.used,memory.free,utilization.gpu,"
        "utilization.memory,temperature.gpu,power.draw,power.limit,clocks.current.graphics,"
        "clocks.current.memory,driver_version"
    )

    def __init__(self, command_runner: CommandRunner = _run) -> None:
        self._run = command_runner

    def get_gpu_devices(self) -> list[GPUDetails]:
        try:
            output = self._run(
                [
                    "nvidia-smi",
                    f"--query-gpu={self.QUERY}",
                    "--format=csv,noheader,nounits",
                ]
            ).stdout
        except (OSError, subprocess.SubprocessError):
            return []
        devices = []
        for line in output.splitlines():
            fields = [field.strip() for field in line.split(",")]
            if len(fields) != 14:
                continue
            devices.append(
                GPUDetails(
                    int(fields[0]),
                    fields[1],
                    GPUVendor.NVIDIA,
                    fields[2],
                    _mib_from_text(fields[3]),
                    _mib_from_text(fields[4]),
                    _mib_from_text(fields[5]),
                    _number_from_text(fields[6]),
                    _number_from_text(fields[7]),
                    _number_from_text(fields[8]),
                    _number_from_text(fields[9]),
                    _number_from_text(fields[10]),
                    _number_from_text(fields[11]),
                    _number_from_text(fields[12]),
                    fields[13],
                    "Unknown",
                    [],
                    "nvidia-smi",
                )
            )
        return devices

    def _device(self, device_index: int) -> GPUDetails | None:
        return next(
            (gpu for gpu in self.get_gpu_devices() if gpu.device_index == device_index),
            None,
        )

    def get_gpu_utilization(self, device_index: int) -> float | None:
        device = self._device(device_index)
        return device.gpu_utilization if device else None

    def get_gpu_temperature(self, device_index: int) -> float | None:
        device = self._device(device_index)
        return device.temperature if device else None

    def get_gpu_power(self, device_index: int) -> dict[str, float | None]:
        device = self._device(device_index)
        return {
            "draw": device.power_draw if device else None,
            "limit": device.power_limit if device else None,
        }


class GenericGPUProvider(GPUProvider):
    def get_gpu_devices(self) -> list[GPUDetails]:
        return []

    def get_gpu_utilization(self, device_index: int) -> None:
        return None

    def get_gpu_temperature(self, device_index: int) -> None:
        return None

    def get_gpu_power(self, device_index: int) -> dict[str, None]:
        return {"draw": None, "limit": None}
