"""Benchmark runner for latency histograms.

CLI usage:
    python -m simulation.benchmark --ticks 10000
    python -m simulation.benchmark --ticks 10000 --report docs/benchmark-results.md
"""

from __future__ import annotations

import argparse
import asyncio
import platform
import statistics
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from contracts import AlertLevel, PerceptionFrame
from engine.negotiation import ReflexNegotiator
from simulation.grid import GridSim, Guard, SquadAgent


@dataclass
class BenchmarkResult:
    samples: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    mean_ms: float
    max_ms: float
    latencies: list[float] | None = None


def default_sim() -> GridSim:
    agents = [SquadAgent(agent_id=f"a{i}", position=(float(i), 2.0)) for i in range(1, 6)]
    guards = [
        Guard(
            guard_id="g1",
            position=(10.0, 10.0),
            patrol_route=[(10.0, 10.0), (12.0, 10.0), (12.0, 12.0)],
        )
    ]
    return GridSim(agents=agents, guards=guards)


async def run_reflex_benchmark(ticks: int = 100, keep_latencies: bool = False) -> BenchmarkResult:
    sim = default_sim()
    agent_ids = [a.agent_id for a in sim.agents]
    negotiator = ReflexNegotiator(squad_id="bench-squad", agent_ids=agent_ids)
    latencies: list[float] = []

    for _ in range(ticks):
        sim.advance_tick()
        frames = sim.all_perceptions()
        start = time.perf_counter()
        await negotiator.negotiate(frames, objective_ref="breach-alpha", tick=sim.tick)
        elapsed_ms = (time.perf_counter() - start) * 1000
        latencies.append(elapsed_ms)

    ordered = sorted(latencies)
    n = len(ordered)

    def percentile(p: float) -> float:
        idx = min(int(n * p), n - 1)
        return ordered[idx]

    return BenchmarkResult(
        samples=n,
        p50_ms=percentile(0.50),
        p95_ms=percentile(0.95),
        p99_ms=percentile(0.99),
        mean_ms=statistics.mean(ordered),
        max_ms=max(ordered),
        latencies=ordered if keep_latencies else None,
    )


def inject_alert_mid_cycle(frames: list[PerceptionFrame]) -> list[PerceptionFrame]:
    """Chaos helper: escalate first agent to ALERT."""
    if not frames:
        return frames
    first = frames[0].model_copy(update={"alert_level": AlertLevel.ALERT})
    return [first, *frames[1:]]


def ascii_histogram(latencies: list[float], buckets: int = 12, width: int = 40) -> str:
    """Render a fixed-width ASCII histogram of latency samples."""
    if not latencies:
        return "(no samples)"
    low, high = min(latencies), max(latencies)
    span = max(high - low, 1e-9)
    counts = [0] * buckets
    for value in latencies:
        idx = min(int((value - low) / span * buckets), buckets - 1)
        counts[idx] += 1
    peak = max(counts)
    lines = []
    for i, count in enumerate(counts):
        lo = low + span * i / buckets
        hi = low + span * (i + 1) / buckets
        bar = "#" * max(1, int(count / peak * width)) if count else ""
        lines.append(f"{lo:7.2f}-{hi:7.2f} ms | {bar} {count}")
    return "\n".join(lines)


def format_report(result: BenchmarkResult) -> str:
    histogram = ascii_histogram(result.latencies or [])
    return f"""# Benchmark Results

Generated: {datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")}

## Environment

| Property | Value |
|----------|-------|
| OS | {platform.system()} {platform.release()} |
| CPU | {platform.processor() or "unknown"} |
| Python | {platform.python_version()} |

## Reflex Path Latency (full perceive-negotiate-commit, 5 agents)

| Metric | Value |
|--------|-------|
| Samples | {result.samples} |
| p50 | {result.p50_ms:.2f} ms |
| p95 | {result.p95_ms:.2f} ms |
| p99 | {result.p99_ms:.2f} ms |
| Mean | {result.mean_ms:.2f} ms |
| Max | {result.max_ms:.2f} ms |

Target: p95 < 150 ms — {"MET" if result.p95_ms < 150 else "NOT MET"}

## Latency Distribution

```
{histogram}
```

Methodology: see [benchmark-methodology.md](benchmark-methodology.md).
Reproduce with `python -m simulation.benchmark --ticks {result.samples}`.
"""


async def _main_async(ticks: int, report_path: Path | None) -> None:
    print(f"Running reflex benchmark: {ticks} ticks, 5 agents...")
    result = await run_reflex_benchmark(ticks=ticks, keep_latencies=True)

    print(f"\n{'Metric':<10} {'Value':>12}")
    print("-" * 23)
    print(f"{'samples':<10} {result.samples:>12}")
    print(f"{'p50':<10} {result.p50_ms:>10.2f}ms")
    print(f"{'p95':<10} {result.p95_ms:>10.2f}ms")
    print(f"{'p99':<10} {result.p99_ms:>10.2f}ms")
    print(f"{'mean':<10} {result.mean_ms:>10.2f}ms")
    print(f"{'max':<10} {result.max_ms:>10.2f}ms")
    print(f"\np95 < 150ms target: {'MET' if result.p95_ms < 150 else 'NOT MET'}")

    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(format_report(result), encoding="utf-8")
        print(f"Report written to {report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="TactixNet reflex latency benchmark")
    parser.add_argument("--ticks", type=int, default=10000)
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("docs/benchmark-results.md"),
        help="Markdown report output path (pass empty string to skip)",
    )
    args = parser.parse_args()
    report = args.report if str(args.report) else None
    asyncio.run(_main_async(args.ticks, report))


if __name__ == "__main__":
    main()
