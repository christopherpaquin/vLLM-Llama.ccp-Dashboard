"""Tests for bounded, read-only model-cache discovery."""

from pathlib import Path

from core.model_cache import ModelCacheDiscovery


def test_model_cache_lists_only_complete_repository_snapshots(tmp_path: Path) -> None:
    (tmp_path / "models--owner--ready" / "snapshots" / "abc").mkdir(parents=True)
    (tmp_path / "models--owner--incomplete").mkdir()
    (tmp_path / "unrelated").mkdir()

    result = ModelCacheDiscovery(tmp_path).discover()

    assert result["available"] is True
    assert result["models"] == [{"repository": "owner/ready", "snapshots": 1}]


def test_model_cache_explains_unavailable_mount(tmp_path: Path) -> None:
    result = ModelCacheDiscovery(tmp_path / "missing").discover()

    assert result["available"] is False
    assert result["models"] == []
    assert "not mounted" in result["reason"]


def test_llama_cpp_cache_lists_gguf_files(tmp_path: Path) -> None:
    model = tmp_path / "models" / "coder-q4.gguf"
    model.parent.mkdir()
    model.write_bytes(b"GGUF")
    (model.parent / "notes.txt").write_text("ignored")

    result = ModelCacheDiscovery(tmp_path, backend="llama_cpp").discover()

    assert result["backend"] == "llama_cpp"
    assert result["models"] == [
        {"repository": "models/coder-q4.gguf", "format": "GGUF", "size_bytes": 4}
    ]
