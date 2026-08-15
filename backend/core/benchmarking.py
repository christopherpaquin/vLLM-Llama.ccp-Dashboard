"""Small, reproducible vLLM endpoint benchmark runner."""

from __future__ import annotations

import json
import os
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
        base_url: str | None = None,
        sender: RequestSender = send_json,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.base_url = (
            base_url or os.getenv("VLLM_BASE_URL", "http://127.0.0.1:8000")
        ).rstrip("/")
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


StreamSender = Callable[
    [urllib.request.Request, float, Callable[[], float]],
    list[tuple[float, dict[str, Any]]],
]


def send_stream(
    request: urllib.request.Request, timeout: float, clock: Callable[[], float]
) -> list[tuple[float, dict[str, Any]]]:
    events = []
    with urllib.request.urlopen(request, timeout=timeout) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8").strip()
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            events.append((clock(), json.loads(line[6:])))
    return events


class InteractiveBenchmarkRunner:
    """Run one deterministic streaming request and measure real TTFT/throughput."""

    PROMPT = "Briefly explain why deterministic benchmarks are useful."

    def __init__(
        self,
        base_url: str | None = None,
        sender: StreamSender = send_stream,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.base_url = (
            base_url or os.getenv("VLLM_BASE_URL", "http://127.0.0.1:8000")
        ).rstrip("/")
        self.sender = sender
        self.clock = clock

    def run(self, model: str, max_tokens: int = 128, seed: int = 1) -> dict[str, Any]:
        payload = {
            "model": model,
            "prompt": self.PROMPT,
            "max_tokens": max_tokens,
            "temperature": 0,
            "seed": seed,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        request = urllib.request.Request(
            f"{self.base_url}/v1/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        started = self.clock()
        events = self.sender(request, 120.0, self.clock)
        finished = self.clock()
        first_token_at = next(
            (
                timestamp
                for timestamp, event in events
                if any(choice.get("text") for choice in event.get("choices", []))
            ),
            None,
        )
        usage = next(
            (event.get("usage") for _, event in reversed(events) if event.get("usage")),
            {},
        )
        output_tokens = int(usage.get("completion_tokens") or 0)
        generation_seconds = finished - first_token_at if first_token_at else None
        return {
            "benchmark_type": "interactive_streaming",
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "output_tokens": output_tokens,
            "max_tokens": max_tokens,
            "ttft_seconds": first_token_at - started if first_token_at else None,
            "e2e_seconds": finished - started,
            "output_tokens_per_second": (
                output_tokens / generation_seconds
                if generation_seconds and generation_seconds > 0
                else None
            ),
            "seed": seed,
            "raw_events": events,
        }
