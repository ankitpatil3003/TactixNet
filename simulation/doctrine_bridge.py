"""Bridge doctrine fields to simulation movement and mission evaluation."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from contracts import RoleEnum
from simulation.bounds import clamp_position
from simulation.grid import GridSim, SquadAgent, _distance
from simulation.movement import move_away, nearest_guard
from simulation.scenario import ScenarioConfig

logger = logging.getLogger(__name__)


def resolve_sim_objective(
    scenario: ScenarioConfig,
    priority_objective: str | None,
) -> tuple[float, float]:
    """Map doctrine priority_objective to grid coordinates."""
    if not priority_objective or priority_objective == scenario.objective:
        return scenario.objective_position

    objectives = scenario.raw.get("objectives", {})
    if priority_objective in objectives:
        pos = objectives[priority_objective]
        return (float(pos[0]), float(pos[1]))

    logger.warning(
        "Unknown priority_objective %r for scenario %s; using default position",
        priority_objective,
        scenario.name,
    )
    return scenario.objective_position


@dataclass
class DoctrineState:
    priority_objective: str = ""
    fallback_plan: str = ""
    role_weights: dict[RoleEnum, float] = field(default_factory=dict)
    objective: tuple[float, float] = (0.0, 0.0)
    objective_label: str = ""
    mapped: bool = True

    @classmethod
    def from_doctrine(
        cls,
        doctrine: dict[str, Any] | None,
        scenario: ScenarioConfig,
    ) -> DoctrineState:
        if doctrine is None:
            objective = scenario.objective_position
            return cls(
                priority_objective=scenario.objective,
                objective=objective,
                objective_label=scenario.objective,
                mapped=True,
            )

        priority = str(doctrine.get("priority_objective", scenario.objective))
        raw_weights = doctrine.get("role_weights", {})
        weights = {
            RoleEnum(role): float(weight)
            for role, weight in raw_weights.items()
            if role in {r.value for r in RoleEnum}
        }
        objective = resolve_sim_objective(scenario, priority)
        mapped = (
            priority == scenario.objective
            or priority in scenario.raw.get("objectives", {})
        )
        return cls(
            priority_objective=priority,
            fallback_plan=str(doctrine.get("fallback_plan", "")),
            role_weights=weights,
            objective=objective,
            objective_label=priority,
            mapped=mapped,
        )

    def update_from_doctrine(self, doctrine: dict[str, Any], scenario: ScenarioConfig) -> None:
        updated = self.from_doctrine(doctrine, scenario)
        self.priority_objective = updated.priority_objective
        self.fallback_plan = updated.fallback_plan
        self.role_weights = updated.role_weights
        self.objective = updated.objective
        self.objective_label = updated.objective_label
        self.mapped = updated.mapped

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "priority_objective": self.priority_objective,
            "fallback_plan": self.fallback_plan,
            "objective_position": list(self.objective),
            "objective_mapped": self.mapped,
        }


def blocks_strategy_refresh(fallback_plan: str) -> bool:
    return fallback_plan == "reflex-only-fallback"


def should_hold_agents(fallback_plan: str) -> bool:
    return fallback_plan == "hold-position"


def should_retreat_agents(fallback_plan: str) -> bool:
    return fallback_plan == "retreat"


def step_retreat(
    sim: GridSim,
    agent: SquadAgent,
    *,
    objective: tuple[float, float],
    step: float = 0.25,
) -> None:
    guard_pos = nearest_guard(sim, agent)
    if guard_pos is None:
        return
    bounds = (float(sim.width), float(sim.height))
    agent.position = clamp_position(
        move_away(
            agent.position,
            guard_pos,
            step,
            objective=objective,
            bounds=bounds,
        ),
        sim.width,
        sim.height,
    )


def movement_step_scale(role: RoleEnum, role_weights: dict[RoleEnum, float]) -> float:
    if not role_weights:
        return 1.0
    weight = role_weights.get(role, 1.0)
    return max(0.25, min(2.0, weight))


def objective_mapping_hint(scenario: ScenarioConfig, priority_objective: str) -> str:
    objective = resolve_sim_objective(scenario, priority_objective)
    if priority_objective == scenario.objective or priority_objective in scenario.raw.get(
        "objectives", {}
    ):
        return f"Mapped to [{objective[0]}, {objective[1]}]"
    return f"Unknown objective; using default [{objective[0]}, {objective[1]}]"


def agents_near_objective(
    sim: GridSim,
    objective: tuple[float, float],
    radius: float,
) -> int:
    return sum(1 for agent in sim.agents if _distance(agent.position, objective) <= radius)
