"""Unit tests for API input validation."""

import pytest
from pydantic import ValidationError

from api.schemas import MemoryValidationRequest, ModelCreate, ProfileCreate


def test_model_requires_canonical_huggingface_repository() -> None:
    with pytest.raises(ValidationError, match="owner/name"):
        ModelCreate(huggingface_repo="../unsafe", friendly_name="Unsafe")


def test_model_rejects_context_above_native_limit() -> None:
    with pytest.raises(ValidationError, match="cannot exceed"):
        ModelCreate(
            huggingface_repo="example/model",
            friendly_name="Example",
            max_context_length=8192,
            current_context_length=16384,
        )


def test_profile_rejects_invalid_gpu_memory_fraction() -> None:
    with pytest.raises(ValidationError):
        ProfileCreate(
            model_id=1,
            name="Unsafe",
            gpu_memory_utilization=1.01,
        )


def test_requests_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        ProfileCreate(model_id=1, name="Typo", gpu_memory_utilisation=0.8)


def test_memory_validation_requires_explicit_positive_capacity() -> None:
    with pytest.raises(ValidationError):
        MemoryValidationRequest(
            model_weights=10,
            runtime_overhead=2,
            kv_cache=4,
            gpu_memory_utilization=0.85,
            available_vram=0,
        )
