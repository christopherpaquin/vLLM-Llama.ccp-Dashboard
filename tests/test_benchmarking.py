"""Tests for the bounded basic benchmark runner."""

from urllib.request import Request

from core.benchmarking import BasicBenchmarkRunner


def test_basic_benchmark_uses_deterministic_bounded_request() -> None:
    calls: list[tuple[Request, float]] = []

    def sender(request: Request, timeout: float) -> dict:
        calls.append((request, timeout))
        return {
            "choices": [{"text": "READY"}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 2},
        }

    times = iter([10.0, 10.5])
    result = BasicBenchmarkRunner(sender=sender, clock=lambda: next(times)).run(
        "test-model", max_tokens=8, seed=1
    )

    assert calls[0][1] == 60
    assert result["prompt_tokens"] == 7
    assert result["output_tokens_per_second"] == 4
    assert result["ttft_seconds"] is None
    assert result["e2e_seconds"] == 0.5
