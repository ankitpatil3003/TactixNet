"""Shared Tier-2 strategy refresh context builders."""

from __future__ import annotations

from typing import Any


def build_strategy_context(
    *,
    tick: int,
    interrupted: bool,
    replan_count: int,
    objective_ref: str,
    mission: dict[str, Any] | None = None,
) -> str:
    mission = mission or {}
    return (
        f"tick={tick} interrupted={interrupted} "
        f"replans={replan_count} objective={objective_ref} "
        f"mission_status={mission.get('status', 'unknown')} "
        f"mission_reason={mission.get('reason', '')} "
        f"compromised={mission.get('compromised_count', 0)} "
        f"agents_at_objective={mission.get('agents_at_objective', 0)}"
    )


def should_request_strategy_refresh(
    *,
    tick: int,
    last_doctrine_tick: int,
    interrupted: bool,
    interval_ticks: int,
) -> bool:
    if interrupted:
        return True
    return tick - last_doctrine_tick >= interval_ticks
