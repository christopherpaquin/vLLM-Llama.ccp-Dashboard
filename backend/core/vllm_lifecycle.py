"""Constrained lifecycle abstractions for an existing vLLM deployment.

Mutation is deliberately disabled until configuration preservation and a
tested restore path exist. This module never creates a replacement container.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


class LifecycleDisabled(RuntimeError):
    """Raised when a caller attempts a lifecycle mutation before safety gates."""


class DockerComposeLifecycleAdapter:
    """Preview-only adapter bound to one detected Compose service."""

    def __init__(self, compose_file: str, service: str) -> None:
        resolved = Path(compose_file).expanduser().resolve()
        if not resolved.is_file() or resolved.suffix not in {".yaml", ".yml"}:
            raise ValueError("compose file must be an existing YAML file")
        if not service or any(
            character
            not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-"
            for character in service
        ):
            raise ValueError("invalid Compose service name")
        self.compose_file = str(resolved)
        self.service = service

    def actions(self) -> dict[str, list[str]]:
        base = ["docker", "compose", "-f", self.compose_file]
        return {
            "start": [*base, "up", "-d", self.service],
            "stop": [*base, "stop", self.service],
            "restart": [*base, "restart", self.service],
            "status": [*base, "ps", "--format", "json", self.service],
        }

    def safety(self) -> dict[str, Any]:
        return {
            "execution_enabled": False,
            "configuration_preserved": False,
            "known_good_restore_implemented": False,
            "reason": "configuration preservation and atomic known-good restore are required",
        }

    def status(self) -> dict[str, Any]:
        try:
            result = subprocess.run(
                self.actions()["status"],
                capture_output=True,
                check=True,
                text=True,
                timeout=10,
            )
            records = [
                json.loads(line) for line in result.stdout.splitlines() if line.strip()
            ]
            return {"reachable": True, "records": records}
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
            return {"reachable": False, "records": []}

    def start_vllm(self) -> bool:
        raise LifecycleDisabled(self.safety()["reason"])

    def stop_vllm(self) -> bool:
        raise LifecycleDisabled(self.safety()["reason"])

    def restart_vllm(self) -> bool:
        raise LifecycleDisabled(self.safety()["reason"])

    def apply_profile(self, profile_id: int) -> bool:
        raise LifecycleDisabled(self.safety()["reason"])


class ExternalVLLMAdapter:
    """Monitoring-only lifecycle representation."""

    def actions(self) -> dict[str, list[str]]:
        return {}

    def safety(self) -> dict[str, Any]:
        return {
            "execution_enabled": False,
            "reason": "deployment is externally managed",
        }

    def start_vllm(self) -> bool:
        raise LifecycleDisabled("deployment is externally managed")

    def stop_vllm(self) -> bool:
        raise LifecycleDisabled("deployment is externally managed")

    def restart_vllm(self) -> bool:
        raise LifecycleDisabled("deployment is externally managed")

    def apply_profile(self, profile_id: int) -> bool:
        raise LifecycleDisabled("deployment is externally managed")
