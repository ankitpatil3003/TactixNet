from pathlib import Path

from simulation.run_demo import (
    DEFAULT_SCENARIO,
    build_sim,
    load_scenario,
    step_agents_toward,
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


def test_agents_step_toward_objective() -> None:
    scenario = load_scenario(Path(DEFAULT_SCENARIO))
    sim = build_sim(scenario)
    start = sim.agents[0].position
    target = (16.0, 16.0)

    for _ in range(10):
        step_agents_toward(sim, target)

    end = sim.agents[0].position
    dist_start = ((target[0] - start[0]) ** 2 + (target[1] - start[1]) ** 2) ** 0.5
    dist_end = ((target[0] - end[0]) ** 2 + (target[1] - end[1]) ** 2) ** 0.5
    assert dist_end < dist_start


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
