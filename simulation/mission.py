"""Mission win/lose evaluation for scenario-driven demos."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from contracts import AlertLevel
from simulation.grid import GridSim, SquadAgent, _distance
from simulation.scenario import ScenarioConfig

MissionStatus = Literal["active", "won", "lost"]


@dataclass
class MissionTracker:
    status: MissionStatus = "active"
    reason: str = ""
    hold_streak: int = 0

    def is_finished(self) -> bool:
        return self.status != "active"


def _agents_at_objective(
    agents: list[SquadAgent],
    objective: tuple[float, float],
    radius: float,
) -> int:
    return sum(1 for agent in agents if _distance(agent.position, objective) <= radius)


def _all_compromised(alert_by_agent: dict[str, AlertLevel]) -> bool:
    if not alert_by_agent:
        return False
    return all(level == AlertLevel.COMPROMISED for level in alert_by_agent.values())


def evaluate_mission(
    sim: GridSim,
    scenario: ScenarioConfig,
    tracker: MissionTracker,
    *,
    alert_by_agent: dict[str, AlertLevel],
    objective_position: tuple[float, float] | None = None,
) -> MissionTracker:
    if tracker.is_finished():
        return tracker

    target = objective_position or scenario.objective_position
    at_objective = _agents_at_objective(
        sim.agents, target, scenario.objective_radius
    )

    if scenario.lose_on_all_compromised and _all_compromised(alert_by_agent):
        tracker.status = "lost"
        tracker.reason = "all agents compromised"
        return tracker

    if scenario.win_condition == "hold_objective":
        if at_objective > 0:
            tracker.hold_streak += 1
        else:
            tracker.hold_streak = 0
        if tracker.hold_streak >= scenario.hold_ticks:
            tracker.status = "won"
            tracker.reason = f"held objective for {scenario.hold_ticks} ticks"
        return tracker

    if at_objective > 0:
        tracker.status = "won"
        tracker.reason = f"{at_objective} agent(s) reached objective"
    return tracker


def mission_snapshot(
    scenario: ScenarioConfig,
    tracker: MissionTracker,
    sim: GridSim,
    *,
    alert_by_agent: dict[str, AlertLevel] | None = None,
    objective_position: tuple[float, float] | None = None,
    doctrine: dict[str, Any] | None = None,
) -> dict[str, Any]:
    alerts = alert_by_agent or {}
    target = objective_position or scenario.objective_position
    at_objective = _agents_at_objective(
        sim.agents, target, scenario.objective_radius
    )
    payload: dict[str, Any] = {
        "objective": scenario.objective,
        "objective_position": list(target),
        "objective_radius": scenario.objective_radius,
        "win_condition": scenario.win_condition,
        "hold_ticks": scenario.hold_ticks,
        "hold_progress": tracker.hold_streak,
        "agents_at_objective": at_objective,
        "status": tracker.status,
        "reason": tracker.reason,
        "compromised_count": sum(
            1 for level in alerts.values() if level == AlertLevel.COMPROMISED
        ),
    }
    if doctrine is not None:
        payload["doctrine"] = doctrine
    return payload
