"""Tests for portable inference-backend configuration."""

from core.inference_config import inference_backend, inference_base_url


def test_llama_cpp_backend_and_url_are_configurable(monkeypatch) -> None:
    monkeypatch.setenv("INFERENCE_BACKEND", "llama.cpp")
    monkeypatch.setenv("INFERENCE_BASE_URL", "http://llama-host:8080/")

    assert inference_backend() == "llama_cpp"
    assert inference_base_url() == "http://llama-host:8080"


def test_unknown_backend_fails_closed_to_vllm(monkeypatch) -> None:
    monkeypatch.setenv("INFERENCE_BACKEND", "unsupported")

    assert inference_backend() == "vllm"
