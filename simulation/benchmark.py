"""Benchmark runner for latency histograms."""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass

from contracts import PerceptionFrame
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


async def run_reflex_benchmark(ticks: int = 100) -> BenchmarkResult:
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

    latencies.sort()
    n = len(latencies)

    def percentile(p: float) -> float:
        idx = min(int(n * p), n - 1)
        return latencies[idx]

    return BenchmarkResult(
        samples=n,
        p50_ms=percentile(0.50),
        p95_ms=percentile(0.95),
        p99_ms=percentile(0.99),
        mean_ms=statistics.mean(latencies),
        max_ms=max(latencies),
    )


def inject_alert_mid_cycle(frames: list[PerceptionFrame]) -> list[PerceptionFrame]:
    """Chaos helper: escalate first agent to ALERT."""
    if not frames:
        return frames
    first = frames[0].model_copy(update={"alert_level": __import__("contracts").AlertLevel.ALERT})
    return [first, *frames[1:]]
