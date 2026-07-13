"""Unit tests for strategy context helpers and graph scheduling flags."""

from __future__ import annotations

import pytest

from engine.graph import STRATEGY_REFRESH_INTERVAL_TICKS, _schedule_strategy
from engine.strategy_context import build_strategy_context, should_request_strategy_refresh
from engine.worker import EngineWorker


def test_build_strategy_context_includes_mission_fields() -> None:
    context = build_strategy_context(
        tick=12,
        interrupted=True,
        replan_count=2,
        objective_ref="flank-point",
        mission={
            "status": "active",
            "reason": "pushing",
            "compromised_count": 1,
            "agents_at_objective": 2,
        },
    )
    assert "tick=12" in context
    assert "interrupted=True" in context
    assert "mission_status=active" in context
    assert "compromised=1" in context
    assert "agents_at_objective=2" in context


def test_should_request_strategy_refresh_on_interval_and_interrupt() -> None:
    assert (
        should_request_strategy_refresh(
            tick=100,
            last_doctrine_tick=0,
            interrupted=False,
            interval_ticks=STRATEGY_REFRESH_INTERVAL_TICKS,
        )
        is True
    )
    assert (
        should_request_strategy_refresh(
            tick=50,
            last_doctrine_tick=0,
            interrupted=False,
            interval_ticks=STRATEGY_REFRESH_INTERVAL_TICKS,
        )
        is False
    )
    assert (
        should_request_strategy_refresh(
            tick=1,
            last_doctrine_tick=0,
            interrupted=True,
            interval_ticks=STRATEGY_REFRESH_INTERVAL_TICKS,
        )
        is True
    )


def test_schedule_strategy_node_sets_request_flag() -> None:
    state = _schedule_strategy(
        {
            "tick": 1,
            "interrupted": True,
            "replan_count": 1,
            "objective_ref": "breach-gate",
            "last_doctrine_tick": 0,
            "strategy_context_hint": "hint-context",
        }
    )
    assert state["strategy_refresh_requested"] is True
    assert state["strategy_context"] == "hint-context"


@pytest.mark.asyncio
async def test_worker_mission_control_updates_runner_snapshot() -> None:
    worker = EngineWorker.__new__(EngineWorker)
    worker._bus = None
    worker._checkpoint_bus = None
    worker._runners = {}

    runner = worker.register_squad("mission-squad", ["a1", "a2"], objective_ref="obj")
    await worker.handle_control(
        "mission-squad",
        {
            "type": "mission",
            "mission": {
                "status": "active",
                "reason": "hold",
                "compromised_count": 0,
                "agents_at_objective": 3,
            },
        },
    )
    assert runner._mission_snapshot["status"] == "active"
    assert runner._mission_snapshot["agents_at_objective"] == 3
