"""Safety tests for lifecycle adapters."""

from pathlib import Path

import pytest

from core.vllm_lifecycle import DockerComposeLifecycleAdapter, LifecycleDisabled


def test_compose_adapter_is_preview_only(tmp_path: Path) -> None:
    compose = tmp_path / "compose.yaml"
    compose.write_text("services: {}\n")
    adapter = DockerComposeLifecycleAdapter(str(compose), "vllm")

    assert adapter.actions()["restart"] == [
        "docker",
        "compose",
        "-f",
        str(compose),
        "restart",
        "vllm",
    ]
    assert adapter.safety()["execution_enabled"] is False
    with pytest.raises(LifecycleDisabled):
        adapter.restart_vllm()


def test_compose_adapter_rejects_service_injection(tmp_path: Path) -> None:
    compose = tmp_path / "compose.yaml"
    compose.write_text("services: {}\n")

    with pytest.raises(ValueError, match="service"):
        DockerComposeLifecycleAdapter(str(compose), "vllm; reboot")
