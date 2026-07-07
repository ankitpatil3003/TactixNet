import pytest

from simulation.benchmark import ascii_histogram, format_report, run_reflex_benchmark


@pytest.mark.asyncio
async def test_reflex_benchmark_p95_under_150ms() -> None:
    result = await run_reflex_benchmark(ticks=50)
    assert result.samples == 50
    assert result.p95_ms < 150.0, f"p95 {result.p95_ms}ms exceeds 150ms budget"


@pytest.mark.asyncio
async def test_benchmark_report_generation() -> None:
    result = await run_reflex_benchmark(ticks=20, keep_latencies=True)
    report = format_report(result)
    assert "## Reflex Path Latency" in report
    assert "p95" in report
    assert "```" in report


def test_ascii_histogram_shape() -> None:
    histogram = ascii_histogram([1.0, 1.1, 1.2, 5.0, 9.9], buckets=5)
    lines = histogram.splitlines()
    assert len(lines) == 5
    assert "ms |" in lines[0]
