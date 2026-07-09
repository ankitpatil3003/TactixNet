from pathlib import Path

import pytest

from contracts import RoleEnum
from simulation.mission import MissionTracker
from simulation.movement import step_agent_by_role
from simulation.run_demo import DEFAULT_SCENARIO, build_sim, world_snapshot
from simulation.scenario import load_scenario


def test_load_default_scenario() -> None:
    scenario = load_scenario(Path(DEFAULT_SCENARIO))
    assert scenario.name == "breach-alpha"
    assert scenario.squad_size == 5
    assert len(scenario.raw["agents"]) == 5
    assert scenario.objective_position == (16.0, 16.0)
    assert scenario.tick_rate_hz == 20.0


def test_load_ambush_scenario() -> None:
    path = Path(__file__).parent.parent / "simulation" / "scenarios" / "ambush.yaml"
    scenario = load_scenario(path)
    assert scenario.name == "ambush"
    assert scenario.objective == "extract-vip"
    assert scenario.tick_rate_hz == 15.0
    assert len(scenario.raw["guards"]) == 2


def test_scenario_squad_size_mismatch_raises() -> None:
    from simulation.scenario import ScenarioConfig

    with pytest.raises(ValueError, match="squad_size"):
        ScenarioConfig.from_dict({"squad_size": 3, "agents": [{"id": "a1"}]})


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
    objective = scenario.objective_position
    step_agent_by_role(sim, sim.agents[0], RoleEnum.BREACH, objective, step=0.5)
    assert sim.agents[0].position != start


def test_world_snapshot_shape() -> None:
    scenario = load_scenario(Path(DEFAULT_SCENARIO))
    sim = build_sim(scenario)
    tracker = MissionTracker()
    sim.advance_tick()
    snapshot = world_snapshot(sim, scenario, tracker)

    assert snapshot["type"] == "world_snapshot"
    assert snapshot["tick"] == 1
    assert len(snapshot["agents"]) == 5
    assert len(snapshot["guards"]) == 1
    assert "alert_level" in snapshot["agents"][0]
    assert "vision_range" in snapshot["guards"][0]
    assert "state" in snapshot["guards"][0]
    assert snapshot["mission"]["status"] == "active"
    assert snapshot["mission"]["objective"] == "breach-gate"
