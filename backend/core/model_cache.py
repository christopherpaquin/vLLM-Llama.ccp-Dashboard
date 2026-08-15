"""Bounded, read-only discovery of Hugging Face hub cache entries."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


class ModelCacheDiscovery:
    """List complete-looking cached model repositories without modifying cache data."""

    def __init__(self, cache_path: Path | None = None, limit: int = 500) -> None:
        self.cache_path = cache_path or Path(
            os.getenv("MODEL_CACHE_PATH", "/host/model-cache")
        )
        self.limit = limit

    def discover(self) -> dict[str, Any]:
        if not self.cache_path.is_dir():
            return {
                "path": str(self.cache_path),
                "available": False,
                "models": [],
                "reason": "Configured model cache is not mounted or readable",
            }
        models = []
        for entry in sorted(self.cache_path.glob("models--*--*"))[: self.limit]:
            if not entry.is_dir():
                continue
            parts = entry.name.split("--", 2)
            if len(parts) != 3 or not (entry / "snapshots").is_dir():
                continue
            snapshots = sum(
                1 for item in (entry / "snapshots").iterdir() if item.is_dir()
            )
            if snapshots:
                models.append(
                    {"repository": f"{parts[1]}/{parts[2]}", "snapshots": snapshots}
                )
        return {
            "path": str(self.cache_path),
            "available": True,
            "models": models,
            "reason": None,
        }
