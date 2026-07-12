"""Tests for doctrine-to-simulation bridge."""

from __future__ import annotations

import pytest

from contracts import RoleEnum
from simulation.doctrine_bridge import (
    DoctrineState,
    blocks_strategy_refresh,
    movement_step_scale,
    resolve_sim_objective,
    should_hold_agents,
    should_retreat_agents,
)
from simulation.driver import build_sim, resolve_scenario
from simulation.movement import step_agent_by_role


def test_resolve_sim_objective_matches_scenario_default() -> None:
    scenario = resolve_scenario("default")
    objective = resolve_sim_objective(scenario, "breach-gate")
    assert objective == scenario.objective_position


def test_resolve_sim_objective_uses_objectives_map() -> None:
    scenario = resolve_scenario("default")
    objective = resolve_sim_objective(scenario, "flank-point")
    assert objective == (8.0, 16.0)


def test_resolve_sim_objective_unknown_falls_back() -> None:
    scenario = resolve_scenario("default")
    objective = resolve_sim_objective(scenario, "unknown-target")
    assert objective == scenario.objective_position


def test_doctrine_state_from_doctrine_maps_objective() -> None:
    scenario = resolve_scenario("default")
    state = DoctrineState.from_doctrine(
        {"priority_objective": "flank-point", "fallback_plan": "hold-position"},
        scenario,
    )
    assert state.objective == (8.0, 16.0)
    assert state.mapped is True
    assert state.fallback_plan == "hold-position"


def test_fallback_plan_flags() -> None:
    assert should_hold_agents("hold-position") is True
    assert should_retreat_agents("retreat") is True
    assert blocks_strategy_refresh("reflex-only-fallback") is True
    assert blocks_strategy_refresh("hold-position") is False


def test_movement_step_scale_clamped() -> None:
    assert movement_step_scale(RoleEnum.BREACH, {RoleEnum.BREACH: 5.0}) == 2.0
    assert movement_step_scale(RoleEnum.BREACH, {}) == 1.0


def test_priority_objective_changes_agent_target() -> None:
    scenario = resolve_scenario("default")
    sim = build_sim(scenario)
    breach = sim.agents[0]
    start = breach.position
    flank_objective = resolve_sim_objective(scenario, "flank-point")
    step_agent_by_role(sim, breach, RoleEnum.BREACH, flank_objective)
    assert breach.position != start
    assert breach.position[0] < scenario.objective_position[0]


def test_replan_multipliers_preserve_base_weights() -> None:
    from engine.negotiation import ReflexNegotiator

    negotiator = ReflexNegotiator(squad_id="s1", agent_ids=["a1", "a2"])
    negotiator.update_bidder_weights({RoleEnum.DISTRACT: 2.0, RoleEnum.BREACH: 0.5})
    negotiator.apply_replan_multipliers({RoleEnum.DISTRACT: 1.5})
    bidder = negotiator._bidders["a1"]
    assert bidder.weights[RoleEnum.DISTRACT] == pytest.approx(3.0)
    negotiator.restore_base_weights()
    assert bidder.weights[RoleEnum.DISTRACT] == pytest.approx(2.0)
