"""Mission win/lose evaluation tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from contracts import AlertLevel
from simulation.grid import GridSim, SquadAgent
from simulation.mission import MissionTracker, evaluate_mission
from simulation.scenario import ScenarioConfig, load_scenario

DEFAULT = Path(__file__).parent.parent / "simulation" / "scenarios" / "default.yaml"
HOLD = Path(__file__).parent.parent / "simulation" / "scenarios" / "hold.yaml"


def _reach_scenario() -> ScenarioConfig:
    return load_scenario(DEFAULT)


def _hold_scenario() -> ScenarioConfig:
    return load_scenario(HOLD)


def test_reach_objective_win() -> None:
    scenario = _reach_scenario()
    sim = GridSim(
        agents=[SquadAgent(agent_id="a1", position=scenario.objective_position)],
        guards=[],
    )
    tracker = MissionTracker()
    result = evaluate_mission(
        sim,
        scenario,
        tracker,
        alert_by_agent={"a1": AlertLevel.CALM},
    )
    assert result.status == "won"
    assert "reached objective" in result.reason


def test_all_compromised_lose() -> None:
    scenario = _reach_scenario()
    sim = GridSim(agents=[SquadAgent(agent_id="a1", position=(1.0, 1.0))], guards=[])
    tracker = MissionTracker()
    result = evaluate_mission(
        sim,
        scenario,
        tracker,
        alert_by_agent={"a1": AlertLevel.COMPROMISED},
    )
    assert result.status == "lost"
    assert result.reason == "all agents compromised"


def test_hold_objective_requires_streak() -> None:
    scenario = _hold_scenario()
    sim = GridSim(
        agents=[SquadAgent(agent_id="a1", position=scenario.objective_position)],
        guards=[],
    )
    tracker = MissionTracker()
    alerts = {"a1": AlertLevel.CALM}
    for _ in range(scenario.hold_ticks - 1):
        tracker = evaluate_mission(sim, scenario, tracker, alert_by_agent=alerts)
        assert tracker.status == "active"
    tracker = evaluate_mission(sim, scenario, tracker, alert_by_agent=alerts)
    assert tracker.status == "won"


def test_hold_streak_resets_when_leaving_zone() -> None:
    scenario = _hold_scenario()
    at_obj = GridSim(
        agents=[SquadAgent(agent_id="a1", position=scenario.objective_position)],
        guards=[],
    )
    away = GridSim(agents=[SquadAgent(agent_id="a1", position=(1.0, 1.0))], guards=[])
    tracker = MissionTracker()
    alerts = {"a1": AlertLevel.CALM}
    for _ in range(5):
        tracker = evaluate_mission(at_obj, scenario, tracker, alert_by_agent=alerts)
    assert tracker.hold_streak == 5
    tracker = evaluate_mission(away, scenario, tracker, alert_by_agent=alerts)
    assert tracker.hold_streak == 0
    assert tracker.status == "active"


def test_invalid_win_condition_raises() -> None:
    with pytest.raises(ValueError, match="win_condition"):
        ScenarioConfig.from_dict(
            {
                "agents": [{"id": "a1"}],
                "win_condition": "invalid",
            }
        )


def test_load_hold_scenario() -> None:
    scenario = _hold_scenario()
    assert scenario.name == "hold-point"
    assert scenario.win_condition == "hold_objective"
    assert scenario.hold_ticks == 25
    assert scenario.objective_radius == 2.0
