"""Shared configuration for supported inference backends."""

from __future__ import annotations

import os


SUPPORTED_BACKENDS = {"vllm", "llama_cpp"}


def inference_backend() -> str:
    value = os.getenv("INFERENCE_BACKEND", "vllm").strip().lower().replace(".", "_")
    return value if value in SUPPORTED_BACKENDS else "vllm"


def inference_base_url() -> str:
    return os.getenv(
        "INFERENCE_BASE_URL",
        os.getenv("VLLM_BASE_URL", "http://127.0.0.1:8000"),
    ).rstrip("/")


def inference_hostname() -> str | None:
    return os.getenv("INFERENCE_HOSTNAME") or os.getenv("VLLM_HOSTNAME")


def backend_display_name(backend: str) -> str:
    return "llama.cpp" if backend == "llama_cpp" else "vLLM"
