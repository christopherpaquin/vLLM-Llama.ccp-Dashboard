"""Unit tests for model resource validation."""

from utils.model_utils import validate_gpu_memory


def test_validate_gpu_memory_reports_fit() -> None:
    result = validate_gpu_memory(10, 2, 4, 0.8, 24)

    assert result["fits"] is True
    assert result["estimated_total"] == 16
    assert result["actual_needed"] == 20


def test_validate_gpu_memory_reports_oom_risk() -> None:
    result = validate_gpu_memory(20, 2, 8, 0.9, 32)

    assert result["fits"] is False
