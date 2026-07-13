"""Per-session live negotiation runner: buffers frames per tick, runs the graph."""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from langgraph.checkpoint.memory import MemorySaver

from contracts import DoctrineUpdate, PerceptionFrame, SquadDirective, alert_level_rank
from contracts.enums import AlertLevel
from engine.checkpoint import RedisCheckpointSaver
from engine.graph import STRATEGY_REFRESH_INTERVAL_TICKS, build_negotiation_graph
from engine.negotiation import ReflexNegotiator
from engine.strategy import StrategyLayer
from engine.strategy_context import build_strategy_context
from simulation.doctrine_bridge import blocks_strategy_refresh

DoctrineCallback = Callable[[DoctrineUpdate], Awaitable[None]]


@dataclass
class CycleResult:
    directive: SquadDirective
    latency_ms: float
    interrupted: bool
    replan_count: int
    objective_ref: str
    recovery_ms: float | None = None
    strategy_refresh_requested: bool = False

    def to_message(self) -> dict[str, Any]:
        message: dict[str, Any] = {
            "type": "directive",
            "directive": self.directive.model_dump(mode="json"),
            "latency_ms": round(self.latency_ms, 2),
            "interrupted": self.interrupted,
            "replan_count": self.replan_count,
            "objective_ref": self.objective_ref,
        }
        if self.recovery_ms is not None:
            message["recovery_ms"] = round(self.recovery_ms, 2)
        return message


@dataclass
class LiveNegotiationRunner:
    """Buffers perception frames per tick and runs negotiation when a tick completes."""

    squad_id: str
    agent_ids: list[str]
    objective_ref: str = "breach-alpha"
    checkpoint_bus: Any | None = None
    _negotiator: ReflexNegotiator = field(init=False)
    _graph: Any = field(init=False)
    _strategy: StrategyLayer = field(default_factory=StrategyLayer, init=False)
    _pending: dict[int, dict[str, PerceptionFrame]] = field(default_factory=dict, init=False)
    _replan_count: int = 0
    _last_doctrine_tick: int = 0
    _strategy_task: asyncio.Task[DoctrineUpdate] | None = field(default=None, init=False)
    _fallback_plan: str = ""
    _mission_snapshot: dict[str, Any] = field(default_factory=dict, init=False)
    _doctrine_callback: DoctrineCallback | None = field(default=None, init=False)
    _interrupt_started_at: float | None = field(default=None, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    def __post_init__(self) -> None:
        self._negotiator = ReflexNegotiator(squad_id=self.squad_id, agent_ids=self.agent_ids)
        checkpointer: Any
        if self.checkpoint_bus is not None and os.environ.get("USE_REDIS_CHECKPOINT") == "1":
            checkpointer = RedisCheckpointSaver(self.checkpoint_bus)
        else:
            checkpointer = MemorySaver()
        self._graph = build_negotiation_graph(self._negotiator).compile(checkpointer=checkpointer)

    def apply_doctrine(self, doctrine: DoctrineUpdate) -> None:
        self._negotiator.update_bidder_weights(doctrine.role_weights)
        self._fallback_plan = doctrine.fallback_plan
        if doctrine.priority_objective:
            self.objective_ref = doctrine.priority_objective

    def set_mission_snapshot(self, mission: dict[str, Any] | None) -> None:
        self._mission_snapshot = dict(mission or {})

    def set_doctrine_callback(self, callback: DoctrineCallback | None) -> None:
        self._doctrine_callback = callback

    def schedule_strategy_refresh(
        self,
        tick: int,
        context: str,
        *,
        after_replan: bool = False,
        on_applied: DoctrineCallback | None = None,
        force: bool = False,
    ) -> None:
        # Without a strategy backend, fallback doctrine resets all weights to 1.0
        # and would overwrite manual doctrine from the console.
        if not self._strategy.available:
            return
        if blocks_strategy_refresh(self._fallback_plan):
            return
        should_refresh = force or after_replan or (
            tick - self._last_doctrine_tick >= STRATEGY_REFRESH_INTERVAL_TICKS
        )
        if not should_refresh:
            return
        if self._strategy_task is not None and not self._strategy_task.done():
            return

        callback = on_applied if on_applied is not None else self._doctrine_callback

        async def _run() -> DoctrineUpdate:
            doctrine = await self._strategy.generate_doctrine(
                self.squad_id, context, self.objective_ref
            )
            self.apply_doctrine(doctrine)
            self._last_doctrine_tick = tick
            if callback is not None:
                await callback(doctrine)
            return doctrine

        self._strategy_task = asyncio.create_task(_run())

    async def ingest_frame(self, frame: PerceptionFrame) -> list[CycleResult]:
        async with self._lock:
            if alert_level_rank(frame.alert_level) >= alert_level_rank(AlertLevel.ALERT):
                if self._interrupt_started_at is None:
                    self._interrupt_started_at = time.perf_counter()

            results: list[CycleResult] = []
            stale_ticks = sorted(t for t in self._pending if t < frame.tick)
            for tick in stale_ticks:
                results.append(await self._run_cycle(tick))

            self._pending.setdefault(frame.tick, {})[frame.agent_id] = frame

            if len(self._pending[frame.tick]) >= len(self.agent_ids):
                results.append(await self._run_cycle(frame.tick))

            return results

    async def _run_cycle(self, tick: int) -> CycleResult:
        frames = list(self._pending.pop(tick, {}).values())
        context_hint = build_strategy_context(
            tick=tick,
            interrupted=False,
            replan_count=self._replan_count,
            objective_ref=self.objective_ref,
            mission=self._mission_snapshot,
        )
        start = time.perf_counter()
        state = await self._graph.ainvoke(
            {
                "squad_id": self.squad_id,
                "tick": tick,
                "objective_ref": self.objective_ref,
                "frames": [f.model_dump() for f in frames],
                "replan_count": self._replan_count,
                "last_doctrine_tick": self._last_doctrine_tick,
                "strategy_context_hint": context_hint,
            },
            {"configurable": {"thread_id": self.squad_id}},
        )
        latency_ms = (time.perf_counter() - start) * 1000

        interrupted = bool(state.get("interrupted"))
        recovery_ms: float | None = None
        if interrupted and self._interrupt_started_at is not None:
            recovery_ms = (time.perf_counter() - self._interrupt_started_at) * 1000
            self._interrupt_started_at = None

        self._replan_count = state.get("replan_count", self._replan_count)
        directive = SquadDirective.model_validate(state["directive"])
        strategy_requested = bool(state.get("strategy_refresh_requested"))
        if strategy_requested:
            # Rebuild context with final interrupted/replan values from the cycle.
            context = build_strategy_context(
                tick=tick,
                interrupted=interrupted,
                replan_count=self._replan_count,
                objective_ref=state.get("objective_ref", self.objective_ref),
                mission=self._mission_snapshot,
            )
            self.schedule_strategy_refresh(
                tick=tick,
                context=context,
                force=True,
            )

        return CycleResult(
            directive=directive,
            latency_ms=latency_ms,
            interrupted=interrupted,
            replan_count=self._replan_count,
            objective_ref=state.get("objective_ref", self.objective_ref),
            recovery_ms=recovery_ms,
            strategy_refresh_requested=strategy_requested,
        )
