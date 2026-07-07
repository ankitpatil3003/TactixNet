"""Per-session live negotiation runner: buffers frames per tick, runs the graph."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from langgraph.checkpoint.memory import MemorySaver

from contracts import PerceptionFrame, SquadDirective
from engine.graph import build_negotiation_graph
from engine.negotiation import ReflexNegotiator


@dataclass
class CycleResult:
    directive: SquadDirective
    latency_ms: float
    interrupted: bool
    replan_count: int
    objective_ref: str

    def to_message(self) -> dict[str, Any]:
        return {
            "type": "directive",
            "directive": self.directive.model_dump(mode="json"),
            "latency_ms": round(self.latency_ms, 2),
            "interrupted": self.interrupted,
            "replan_count": self.replan_count,
            "objective_ref": self.objective_ref,
        }


@dataclass
class LiveNegotiationRunner:
    """Buffers perception frames per tick and runs negotiation when a tick completes.

    A tick is complete when every squad agent has reported a frame for it. If a
    frame for a newer tick arrives while an older tick is incomplete, the older
    tick is flushed with whatever frames are present (slow agents forfeit).
    """

    squad_id: str
    agent_ids: list[str]
    objective_ref: str = "breach-alpha"
    _negotiator: ReflexNegotiator = field(init=False)
    _graph: Any = field(init=False)
    _pending: dict[int, dict[str, PerceptionFrame]] = field(default_factory=dict, init=False)
    _replan_count: int = 0

    def __post_init__(self) -> None:
        self._negotiator = ReflexNegotiator(squad_id=self.squad_id, agent_ids=self.agent_ids)
        self._graph = build_negotiation_graph(self._negotiator).compile(
            checkpointer=MemorySaver()
        )

    async def ingest_frame(self, frame: PerceptionFrame) -> list[CycleResult]:
        """Add a frame; return cycle results for any tick that became runnable."""
        results: list[CycleResult] = []

        # Flush strictly older, incomplete ticks before buffering the new frame.
        stale_ticks = sorted(t for t in self._pending if t < frame.tick)
        for tick in stale_ticks:
            results.append(await self._run_cycle(tick))

        self._pending.setdefault(frame.tick, {})[frame.agent_id] = frame

        if len(self._pending[frame.tick]) >= len(self.agent_ids):
            results.append(await self._run_cycle(frame.tick))

        return results

    async def _run_cycle(self, tick: int) -> CycleResult:
        frames = list(self._pending.pop(tick, {}).values())
        start = time.perf_counter()
        state = await self._graph.ainvoke(
            {
                "squad_id": self.squad_id,
                "tick": tick,
                "objective_ref": self.objective_ref,
                "frames": [f.model_dump() for f in frames],
                "replan_count": self._replan_count,
            },
            {"configurable": {"thread_id": self.squad_id}},
        )
        latency_ms = (time.perf_counter() - start) * 1000

        self._replan_count = state.get("replan_count", self._replan_count)
        directive = SquadDirective.model_validate(state["directive"])
        return CycleResult(
            directive=directive,
            latency_ms=latency_ms,
            interrupted=bool(state.get("interrupted")),
            replan_count=self._replan_count,
            objective_ref=state.get("objective_ref", self.objective_ref),
        )
