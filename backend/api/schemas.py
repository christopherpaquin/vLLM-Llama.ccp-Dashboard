"""Validated request schemas for the management API."""

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


HF_REPOSITORY_PATTERN = re.compile(
    r"^(?=.{3,128}$)[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$"
)


class StrictRequest(BaseModel):
    """Base request that rejects misspelled or unsupported fields."""

    model_config = ConfigDict(
        extra="forbid",
        protected_namespaces=(),
        str_strip_whitespace=True,
    )


def validate_huggingface_repository(value: str | None) -> str | None:
    """Validate a canonical Hugging Face ``owner/repository`` identifier."""
    if value is None:
        return None
    if not HF_REPOSITORY_PATTERN.fullmatch(value):
        raise ValueError("must be a Hugging Face repository in owner/name format")
    return value


class ModelCreate(StrictRequest):
    huggingface_repo: str
    friendly_name: str = Field(min_length=1, max_length=200)
    architecture: str | None = Field(default=None, max_length=100)
    total_parameters: str | None = Field(default=None, max_length=50)
    active_parameters: str | None = Field(default=None, max_length=50)
    quantization: str | None = Field(default=None, max_length=50)
    weight_size: str | None = Field(default=None, max_length=50)
    estimated_vram: str | None = Field(default=None, max_length=50)
    max_context_length: int | None = Field(default=None, ge=1)
    current_context_length: int = Field(default=32768, ge=1)
    vllm_compatible: bool = False
    installed: bool = False
    download_progress: int = Field(default=0, ge=0, le=100)
    compatibility_state: str = Field(default="Unknown", max_length=50)

    _validate_repository = field_validator("huggingface_repo")(
        validate_huggingface_repository
    )

    @model_validator(mode="after")
    def context_does_not_exceed_native(self) -> "ModelCreate":
        if (
            self.max_context_length is not None
            and self.current_context_length > self.max_context_length
        ):
            raise ValueError(
                "current context length cannot exceed native context length"
            )
        return self


class ModelUpdate(StrictRequest):
    huggingface_repo: str | None = None
    friendly_name: str | None = Field(default=None, min_length=1, max_length=200)
    architecture: str | None = Field(default=None, max_length=100)
    total_parameters: str | None = Field(default=None, max_length=50)
    active_parameters: str | None = Field(default=None, max_length=50)
    quantization: str | None = Field(default=None, max_length=50)
    weight_size: str | None = Field(default=None, max_length=50)
    estimated_vram: str | None = Field(default=None, max_length=50)
    max_context_length: int | None = Field(default=None, ge=1)
    current_context_length: int | None = Field(default=None, ge=1)
    vllm_compatible: bool | None = None
    installed: bool | None = None
    download_progress: int | None = Field(default=None, ge=0, le=100)
    compatibility_state: str | None = Field(default=None, max_length=50)

    _validate_repository = field_validator("huggingface_repo")(
        validate_huggingface_repository
    )


class ProfileCreate(StrictRequest):
    model_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    max_model_len: int = Field(default=32768, ge=1)
    gpu_memory_utilization: float = Field(default=0.85, gt=0, le=1)
    max_num_seqs: int = Field(default=4, ge=1)
    max_num_batched_tokens: str = Field(default="auto", max_length=20)
    enable_prefix_caching: bool = True
    kv_cache_dtype: str = Field(default="auto", max_length=50)
    dtype: str = Field(default="auto", max_length=50)
    cpu_offload_gb: int = Field(default=0, ge=0)
    swap_space: int = Field(default=4, ge=0)


class ProfileUpdate(StrictRequest):
    model_id: int | None = Field(default=None, gt=0)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    max_model_len: int | None = Field(default=None, ge=1)
    gpu_memory_utilization: float | None = Field(default=None, gt=0, le=1)
    max_num_seqs: int | None = Field(default=None, ge=1)
    max_num_batched_tokens: str | None = Field(default=None, max_length=20)
    enable_prefix_caching: bool | None = None
    kv_cache_dtype: str | None = Field(default=None, max_length=50)
    dtype: str | None = Field(default=None, max_length=50)
    cpu_offload_gb: int | None = Field(default=None, ge=0)
    swap_space: int | None = Field(default=None, ge=0)


class MemoryValidationRequest(StrictRequest):
    model_weights: float = Field(ge=0)
    runtime_overhead: float = Field(ge=0)
    kv_cache: float = Field(ge=0)
    gpu_memory_utilization: float = Field(gt=0, le=1)
    available_vram: float = Field(gt=0)


class BasicBenchmarkRequest(StrictRequest):
    model_id: int = Field(gt=0)
    profile_id: int = Field(gt=0)
    max_tokens: int = Field(default=8, ge=1, le=256)
    seed: int = 1


class KnownGoodRequest(StrictRequest):
    profile_id: int = Field(gt=0)
    runtime_snapshot_id: int = Field(gt=0)
    benchmark_validated: bool = False
