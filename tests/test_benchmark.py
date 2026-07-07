import pytest

from simulation.benchmark import run_reflex_benchmark


@pytest.mark.asyncio
async def test_reflex_benchmark_p95_under_150ms() -> None:
    result = await run_reflex_benchmark(ticks=50)
    assert result.samples == 50
    assert result.p95_ms < 150.0, f"p95 {result.p95_ms}ms exceeds 150ms budget"
