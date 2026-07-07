from pathlib import Path

from contracts import RoleEnum
from simulation.movement import step_agent_by_role
from simulation.run_demo import (
    DEFAULT_SCENARIO,
    build_sim,
    load_scenario,
    world_snapshot,
)


def test_load_default_scenario() -> None:
    scenario = load_scenario(Path(DEFAULT_SCENARIO))
    assert scenario["name"] == "breach-alpha"
    assert len(scenario["agents"]) == 5
    assert scenario["objective_position"] == [16, 16]


def test_build_sim_from_scenario() -> None:
    scenario = load_scenario(Path(DEFAULT_SCENARIO))
    sim = build_sim(scenario)
    assert len(sim.agents) == 5
    assert len(sim.guards) == 1
    assert sim.guards[0].patrol_route[0] == (10.0, 10.0)


def test_role_based_movement_advances_agent() -> None:
    scenario = load_scenario(Path(DEFAULT_SCENARIO))
    sim = build_sim(scenario)
    start = sim.agents[0].position
    objective = tuple(scenario["objective_position"])
    step_agent_by_role(sim, sim.agents[0], RoleEnum.BREACH, objective, step=0.5)
    assert sim.agents[0].position != start


def test_world_snapshot_shape() -> None:
    scenario = load_scenario(Path(DEFAULT_SCENARIO))
    sim = build_sim(scenario)
    sim.advance_tick()
    snapshot = world_snapshot(sim)

    assert snapshot["type"] == "world_snapshot"
    assert snapshot["tick"] == 1
    assert len(snapshot["agents"]) == 5
    assert len(snapshot["guards"]) == 1
    assert "alert_level" in snapshot["agents"][0]
    assert "vision_range" in snapshot["guards"][0]
    assert "state" in snapshot["guards"][0]
