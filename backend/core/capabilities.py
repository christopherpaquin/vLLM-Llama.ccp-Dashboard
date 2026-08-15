"""
vLLM Management Portal - Adapters and Capabilities Framework
"""

import platform
import subprocess
import json
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum


class OperatingSystem(Enum):
    UBUNTU = "ubuntu"
    FEDORA = "fedora"
    RHEL = "rhel"
    OTHER = "other"


class GPUVendor(Enum):
    AMD = "amd"
    NVIDIA = "nvidia"
    OTHER = "other"


class ContainerRuntime(Enum):
    DOCKER = "docker"
    PODMAN = "podman"
    QUADLET = "quadlet"
    EXTERNAL = "external"


class LifecycleMode(Enum):
    MANAGED = "managed"
    EXTERNAL = "external"


@dataclass
class HostCapabilities:
    """Data structure for host capabilities discovery"""

    hostname: str
    os: OperatingSystem
    os_version: str
    kernel: str
    architecture: str
    uptime: str
    selinux: str
    apparmor: str

    # GPU capabilities
    gpus: List[Dict]  # List of GPUDeviceInfo objects

    # Runtime capabilities
    container_runtime: ContainerRuntime
    docker_available: bool
    podman_available: bool
    quadlet_available: bool
    compose_available: bool

    # vLLM capabilities
    vllm_deployed: bool
    vllm_api_reachable: bool
    vllm_metrics_reachable: bool
    vllm_version: str
    vllm_image: str

    # Lifecycle capabilities
    lifecycle_mode: LifecycleMode
    lifecycle_provider: str

    # Storage capabilities
    model_storage_path: str
    cache_storage_path: str

    def to_dict(self) -> Dict:
        """Convert capabilities object to dictionary for storage"""
        return {
            "hostname": self.hostname,
            "os": self.os.value,
            "os_version": self.os_version,
            "kernel": self.kernel,
            "architecture": self.architecture,
            "uptime": self.uptime,
            "selinux": self.selinux,
            "apparmor": self.apparmor,
            "gpus": self.gpus,
            "container_runtime": self.container_runtime.value,
            "docker_available": self.docker_available,
            "podman_available": self.podman_available,
            "quadlet_available": self.quadlet_available,
            "compose_available": self.compose_available,
            "vllm_deployed": self.vllm_deployed,
            "vllm_api_reachable": self.vllm_api_reachable,
            "vllm_metrics_reachable": self.vllm_metrics_reachable,
            "vllm_version": self.vllm_version,
            "vllm_image": self.vllm_image,
            "lifecycle_mode": self.lifecycle_mode.value,
            "lifecycle_provider": self.lifecycle_provider,
            "model_storage_path": self.model_storage_path,
            "cache_storage_path": self.cache_storage_path,
        }


class SystemProvider(ABC):
    """Abstract base class for system information providers"""

    @abstractmethod
    def get_os_info(self) -> Dict[str, str]:
        """Get OS information"""
        pass

    @abstractmethod
    def get_system_info(self) -> Dict[str, str]:
        """Get general system information"""
        pass

    @abstractmethod
    def get_uptime(self) -> str:
        """Get system uptime"""
        pass

    @abstractmethod
    def get_security_info(self) -> Dict[str, str]:
        """Get security framework information"""
        pass


class GPUDetails:
    """Data structure for GPU information"""

    def __init__(
        self,
        device_index: int,
        uuid: str,
        vendor: GPUVendor,
        model: str,
        vram_total: Optional[float],
        vram_used: Optional[float],
        vram_free: Optional[float],
        gpu_utilization: Optional[float],
        memory_utilization: Optional[float],
        temperature: Optional[float],
        power_draw: Optional[float],
        power_limit: Optional[float],
        core_clock: Optional[float],
        memory_clock: Optional[float],
        driver_version: str,
        compute_runtime_version: str,
        processes: List[Dict],
        telemetry_provider: str = "unavailable",
    ):
        self.device_index = device_index
        self.uuid = uuid
        self.vendor = vendor
        self.model = model
        self.vram_total = vram_total
        self.vram_used = vram_used
        self.vram_free = vram_free
        self.gpu_utilization = gpu_utilization
        self.memory_utilization = memory_utilization
        self.temperature = temperature
        self.power_draw = power_draw
        self.power_limit = power_limit
        self.core_clock = core_clock
        self.memory_clock = memory_clock
        self.driver_version = driver_version
        self.compute_runtime_version = compute_runtime_version
        self.processes = processes
        self.telemetry_provider = telemetry_provider

    def to_dict(self) -> Dict:
        return {
            "device_index": self.device_index,
            "uuid": self.uuid,
            "vendor": self.vendor.value,
            "model": self.model,
            "vram_total": self.vram_total,
            "vram_used": self.vram_used,
            "vram_free": self.vram_free,
            "gpu_utilization": self.gpu_utilization,
            "memory_utilization": self.memory_utilization,
            "temperature": self.temperature,
            "power_draw": self.power_draw,
            "power_limit": self.power_limit,
            "core_clock": self.core_clock,
            "memory_clock": self.memory_clock,
            "driver_version": self.driver_version,
            "compute_runtime_version": self.compute_runtime_version,
            "processes": self.processes,
            "telemetry_provider": self.telemetry_provider,
        }


class GPUProvider(ABC):
    """Abstract base class for GPU telemetry providers"""

    @abstractmethod
    def get_gpu_devices(self) -> List[GPUDetails]:
        """Get list of GPU devices with detailed information"""
        pass

    @abstractmethod
    def get_gpu_utilization(self, device_index: int) -> float:
        """Get GPU utilization for a specific device"""
        pass

    @abstractmethod
    def get_gpu_temperature(self, device_index: int) -> float:
        """Get GPU temperature for a specific device"""
        pass

    @abstractmethod
    def get_gpu_power(self, device_index: int) -> Dict[str, float]:
        """Get GPU power usage for a specific device"""
        pass


class ContainerRuntimeProvider(ABC):
    """Abstract base class for container runtime providers"""

    @abstractmethod
    def get_runtime_info(self) -> Dict[str, str]:
        """Get container runtime information"""
        pass

    @abstractmethod
    def is_runtime_available(self) -> bool:
        """Check if runtime is available"""
        pass


class VLLMLifecycleProvider(ABC):
    """Abstract base class for VLLM lifecycle providers"""

    @abstractmethod
    def start_vllm(self) -> bool:
        """Start VLLM deployment"""
        pass

    @abstractmethod
    def stop_vllm(self) -> bool:
        """Stop VLLM deployment"""
        pass

    @abstractmethod
    def restart_vllm(self) -> bool:
        """Restart VLLM deployment"""
        pass

    @abstractmethod
    def apply_profile(self, profile_id: int) -> bool:
        """Apply a profile to the VLLM deployment"""
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, str]:
        """Get VLLM deployment status"""
        pass


class SystemProviderImpl(SystemProvider):
    """Concrete implementation for system information discovery"""

    def __init__(self):
        self._os_info = None
        self._system_info = None
        self._security_info = None

    def get_os_info(self) -> Dict[str, str]:
        """Get OS information from /etc/os-release"""
        if self._os_info:
            return self._os_info

        # Try to get OS info from /etc/os-release
        try:
            with open("/etc/os-release", "r") as f:
                os_release_data = {}
                for line in f:
                    if "=" in line:
                        key, value = line.strip().split("=", 1)
                        os_release_data[key] = value.strip('"')

                # Determine OS type
                os_type = OperatingSystem.OTHER
                if "ubuntu" in os_release_data.get("ID", "").lower():
                    os_type = OperatingSystem.UBUNTU
                elif "fedora" in os_release_data.get("ID", "").lower():
                    os_type = OperatingSystem.FEDORA
                elif "rhel" in os_release_data.get("ID", "").lower():
                    os_type = OperatingSystem.RHEL

                self._os_info = {
                    "os": os_type,
                    "version": os_release_data.get("VERSION_ID", "unknown"),
                    "name": os_release_data.get("NAME", "unknown"),
                }

        except FileNotFoundError:
            # Fallback for non-Linux systems
            self._os_info = {
                "os": OperatingSystem.OTHER,
                "version": platform.version(),
                "name": platform.system(),
            }

        return self._os_info

    def get_system_info(self) -> Dict[str, str]:
        """Get general system information"""
        if self._system_info:
            return self._system_info

        self._system_info = {
            "hostname": platform.node(),
            "kernel": platform.release(),
            "architecture": platform.machine(),
        }

        return self._system_info

    def get_uptime(self) -> str:
        """Get system uptime"""
        try:
            with open("/proc/uptime", "r") as f:
                uptime_seconds = float(f.read().split()[0])
                hours = int(uptime_seconds // 3600)
                minutes = int((uptime_seconds % 3600) // 60)
                return f"{hours}h {minutes}m"
        except (OSError, ValueError, IndexError):
            return "Unknown"

    def get_security_info(self) -> Dict[str, str]:
        """Get security framework information"""
        if self._security_info:
            return self._security_info

        try:
            # Check SELinux
            selinux_status = "not active"
            try:
                result = subprocess.run(
                    ["sestatus"], capture_output=True, text=True, check=True
                )
                if "enabled" in result.stdout.lower():
                    selinux_status = "enabled"
                elif "permissive" in result.stdout.lower():
                    selinux_status = "permissive"
            except (OSError, subprocess.SubprocessError):
                pass  # SELinux might not be installed

            # Check AppArmor
            apparmor_status = "disabled"
            try:
                result = subprocess.run(
                    ["aa-status", "--json"], capture_output=True, text=True, check=True
                )
                if result.returncode == 0 and "enabled" in result.stdout.lower():
                    apparmor_status = "enabled"
            except (OSError, subprocess.SubprocessError):
                pass  # AppArmor might not be installed

            self._security_info = {
                "selinux": selinux_status,
                "apparmor": apparmor_status,
            }
        except (OSError, subprocess.SubprocessError):
            self._security_info = {"selinux": "unknown", "apparmor": "unknown"}

        return self._security_info


class GPUProviderFactory:
    """Factory for creating appropriate GPU providers based on hardware detected"""

    _providers = {}

    @classmethod
    def get_provider(cls, vendor: GPUVendor) -> GPUProvider:
        """Get appropriate GPU provider for vendor"""
        if vendor not in cls._providers:
            if vendor == GPUVendor.AMD:
                cls._providers[vendor] = AMDGPUProvider()
            elif vendor == GPUVendor.NVIDIA:
                cls._providers[vendor] = NVGPUProvider()
            else:
                cls._providers[vendor] = GenericGPUProvider()

        return cls._providers[vendor]


class AMDGPUProvider(GPUProvider):
    """AMD GPU provider using rocm-smi or amd-smi"""

    def __init__(self):
        self._gpu_devices = []

    def get_gpu_devices(self) -> List[GPUDetails]:
        """Get AMD GPU devices information"""
        # Check if rocm-smi or amd-smi is available
        try:
            # Try rocm-smi first (modern ROCm)
            result = subprocess.run(
                ["rocm-smi", "--showmem", "--json"],
                capture_output=True,
                text=True,
                check=True,
            )
            # Parse the JSON output - simplified version
            data = json.loads(result.stdout)
            return self._parse_amd_output(data)
        except (subprocess.CalledProcessError, FileNotFoundError):
            try:
                # Fallback to amd-smi
                result = subprocess.run(
                    ["amd-smi", "--showmem", "--json"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                data = json.loads(result.stdout)
                return self._parse_amd_output(data)
            except (subprocess.CalledProcessError, FileNotFoundError):
                # Fallback to basic sysfs information
                return self._parse_sysfs()

    def _parse_amd_output(self, data: Dict) -> List[GPUDetails]:
        """Parse AMD GPU data from rocm-smi or amd-smi output"""
        # Simplified implementation - in reality this would parse detailed JSON
        return []

    def _parse_sysfs(self) -> List[GPUDetails]:
        """Parse GPU information from sysfs"""
        # This is a simplified version for demonstration
        return []

    def get_gpu_utilization(self, device_index: int) -> float:
        """Get GPU utilization for AMD device"""
        return 0.0

    def get_gpu_temperature(self, device_index: int) -> float:
        """Get GPU temperature for AMD device"""
        return 0.0

    def get_gpu_power(self, device_index: int) -> Dict[str, float]:
        """Get GPU power usage for AMD device"""
        return {"draw": 0.0, "limit": 0.0}


class NVGPUProvider(GPUProvider):
    """NVIDIA GPU provider using nvidia-smi or NVML"""

    def __init__(self):
        self._gpu_devices = []

    def get_gpu_devices(self) -> List[GPUDetails]:
        """Get NVIDIA GPU devices information"""
        # Check if nvidia-smi is available
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-computedriver-version",
                    "--query-gpu=utilization.gpu,memory.used,memory.free",
                    "--format=csv",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            # Parse nvidia-smi output
            return self._parse_nvidia_output(result.stdout)
        except (subprocess.CalledProcessError, FileNotFoundError):
            return []

    def _parse_nvidia_output(self, output: str) -> List[GPUDetails]:
        """Parse nvidia-smi output"""
        # Simplified implementation for demonstration
        return []

    def get_gpu_utilization(self, device_index: int) -> float:
        """Get GPU utilization for NVIDIA device"""
        return 0.0

    def get_gpu_temperature(self, device_index: int) -> float:
        """Get GPU temperature for NVIDIA device"""
        return 0.0

    def get_gpu_power(self, device_index: int) -> Dict[str, float]:
        """Get GPU power usage for NVIDIA device"""
        return {"draw": 0.0, "limit": 0.0}


class GenericGPUProvider(GPUProvider):
    """Generic GPU provider for unknown vendors"""

    def get_gpu_devices(self) -> List[GPUDetails]:
        """Return empty list for unknown GPU vendors"""
        return []

    def get_gpu_utilization(self, device_index: int) -> float:
        """Generic GPU utilization"""
        return 0.0

    def get_gpu_temperature(self, device_index: int) -> float:
        """Generic GPU temperature"""
        return 0.0

    def get_gpu_power(self, device_index: int) -> Dict[str, float]:
        """Generic GPU power"""
        return {"draw": 0.0, "limit": 0.0}


class ContainerRuntimeProviderImpl(ContainerRuntimeProvider):
    """Concrete implementation for detecting container runtimes"""

    def __init__(self):
        self._runtime_info = {}
        self._runtime_available = False

    def get_runtime_info(self) -> Dict[str, str]:
        """Get container runtime information"""
        # Detect available runtimes
        available_runtimes = []

        # Check Docker
        try:
            subprocess.run(["docker", "--version"], capture_output=True, check=True)
            available_runtimes.append("docker")
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

        # Check Podman
        try:
            subprocess.run(["podman", "--version"], capture_output=True, check=True)
            available_runtimes.append("podman")
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

        # Check Quadlet
        try:
            # Check if this is a valid system with quadlet
            result = subprocess.run(
                ["which", "quadlet"], capture_output=True, text=True
            )
            if result.returncode == 0:
                available_runtimes.append("quadlet")
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

        # Determine primary runtime
        runtime = ContainerRuntime.EXTERNAL
        if "docker" in available_runtimes:
            runtime = ContainerRuntime.DOCKER
        elif "podman" in available_runtimes:
            runtime = ContainerRuntime.PODMAN
        elif "quadlet" in available_runtimes:
            runtime = ContainerRuntime.QUADLET

        return {
            "primary_runtime": runtime.value,
            "available_runtimes": available_runtimes,
        }

    def is_runtime_available(self) -> bool:
        """Check if at least one container runtime is available"""
        try:
            # Try to detect any container runtime
            subprocess.run(["docker", "--version"], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            try:
                subprocess.run(["podman", "--version"], capture_output=True, check=True)
                return True
            except (subprocess.CalledProcessError, FileNotFoundError):
                return False


class VLLMLifecycleProviderImpl(VLLMLifecycleProvider):
    """Concrete implementation for managing VLLM lifecycle"""

    def __init__(self):
        self._vllm_info = {}

    def start_vllm(self) -> bool:
        """Start VLLM deployment"""
        # Implementation varies by deployment method
        return True

    def stop_vllm(self) -> bool:
        """Stop VLLM deployment"""
        return True

    def restart_vllm(self) -> bool:
        """Restart VLLM deployment"""
        return True

    def apply_profile(self, profile_id: int) -> bool:
        """Apply a profile to the VLLM deployment"""
        return True

    def get_status(self) -> Dict[str, str]:
        """Get VLLM deployment status"""
        return {"status": "unknown", "version": "unknown", "api_endpoint": "unknown"}


# Main capability discovery function
def discover_host_capabilities() -> HostCapabilities:
    """Discover and return host capabilities"""

    # System discovery
    system_provider = SystemProviderImpl()
    os_info = system_provider.get_os_info()
    system_info = system_provider.get_system_info()
    security_info = system_provider.get_security_info()
    uptime = system_provider.get_uptime()

    # Runtime discovery
    ContainerRuntimeProviderImpl().get_runtime_info()

    # For now, return a stub with some basic information
    return HostCapabilities(
        hostname=system_info.get("hostname", "unknown"),
        os=OperatingSystem.OTHER,  # Will be set dynamically
        os_version=os_info.get("version", "unknown"),
        kernel=system_info.get("kernel", "unknown"),
        architecture=system_info.get("architecture", "unknown"),
        uptime=uptime,
        selinux=security_info.get("selinux", "unknown"),
        apparmor=security_info.get("apparmor", "unknown"),
        gpus=[],  # To be populated by GPU discovery
        container_runtime=ContainerRuntime.EXTERNAL,
        docker_available=False,
        podman_available=False,
        quadlet_available=False,
        compose_available=False,
        vllm_deployed=False,
        vllm_api_reachable=False,
        vllm_metrics_reachable=False,
        vllm_version="unknown",
        vllm_image="unknown",
        lifecycle_mode=LifecycleMode.EXTERNAL,
        lifecycle_provider="none",
        model_storage_path="/var/cache/huggingface",
        cache_storage_path="/var/cache/huggingface",
    )
