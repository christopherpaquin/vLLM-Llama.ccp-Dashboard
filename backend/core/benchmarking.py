"""Small, reproducible vLLM endpoint benchmark runner."""

from __future__ import annotations

import json
import time
import urllib.request
from collections.abc import Callable
from typing import Any


RequestSender = Callable[[urllib.request.Request, float], dict[str, Any]]


def send_json(request: urllib.request.Request, timeout: float) -> dict[str, Any]:
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


class BasicBenchmarkRunner:
    """Run a bounded, non-streaming completion benchmark.

    Non-streaming responses cannot provide TTFT, TPOT, or ITL reliably, so
    those values remain unavailable rather than being inferred.
    """

    PROMPT = "Return only the word READY."

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        sender: RequestSender = send_json,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.sender = sender
        self.clock = clock

    def run(self, model: str, max_tokens: int = 8, seed: int = 1) -> dict[str, Any]:
        payload = {
            "model": model,
            "prompt": self.PROMPT,
            "max_tokens": max_tokens,
            "temperature": 0,
            "seed": seed,
        }
        request = urllib.request.Request(
            f"{self.base_url}/v1/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        started = self.clock()
        response = self.sender(request, 60.0)
        elapsed = self.clock() - started
        usage = response.get("usage") or {}
        output_tokens = int(usage.get("completion_tokens") or 0)
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        return {
            "benchmark_type": "basic_endpoint",
            "prompt": self.PROMPT,
            "prompt_tokens": prompt_tokens,
            "output_tokens": output_tokens,
            "max_tokens": max_tokens,
            "concurrency": 1,
            "requests": 1,
            "warmup_requests": 0,
            "seed": seed,
            "e2e_seconds": elapsed,
            "output_tokens_per_second": output_tokens / elapsed
            if elapsed > 0
            else None,
            "ttft_seconds": None,
            "tpot_seconds": None,
            "itl_seconds": None,
            "raw_response": response,
        }
