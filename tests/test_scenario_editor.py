"""Tests for squad scenario customization (guards, objective)."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from gateway import app as app_module
from gateway.app import app
from gateway.simulation_runner import SimulationRunner
from simulation.driver import build_sim, resolve_scenario_for_squad
from simulation.scenario import ScenarioConfig


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        app_module._simulation_runner = SimulationRunner("http://testserver")
        yield test_client


def test_list_scenarios_includes_guard_count(client: TestClient) -> None:
    body = client.get("/scenarios").json()
    default = next(s for s in body["scenarios"] if s["name"] == "default")
    assert default["guard_count"] == 1
    ambush = next(s for s in body["scenarios"] if s["name"] == "ambush")
    assert ambush["guard_count"] == 2


def test_patch_scenario_adds_guard(client: TestClient) -> None:
    squad_id = client.post("/squads/from-scenario", json={"scenario": "default"}).json()[
        "squad_id"
    ]
    scenario = client.get(f"/squads/{squad_id}/scenario").json()["scenario"]
    guards = list(scenario["guards"])
    guards.append(
        {
            "id": "g2",
            "position": [14.0, 14.0],
            "patrol": [[14.0, 14.0], [16.0, 14.0]],
            "vision_range": 3.5,
            "vision_angle_deg": 120,
            "patrol_speed": 0.2,
        }
    )
    updated = client.patch(
        f"/squads/{squad_id}/scenario",
        json={
            "guards": guards,
            "objective_position": [16, 16],
            "grid_size": 20,
        },
    )
    assert updated.status_code == 200
    saved = client.get(f"/squads/{squad_id}/scenario").json()["scenario"]
    assert len(saved["guards"]) == 2

    listed = client.get("/squads").json()
    row = next(s for s in listed["squads"] if s["squad_id"] == squad_id)
    assert row["guard_count"] == 2


def test_simulation_uses_patched_guard_count(client: TestClient) -> None:
    squad_id = client.post("/squads/from-scenario", json={"scenario": "default"}).json()[
        "squad_id"
    ]
    scenario = client.get(f"/squads/{squad_id}/scenario").json()["scenario"]
    guards = list(scenario["guards"])
    guards.append(
        {
            "id": "g2",
            "position": [15.0, 15.0],
            "patrol": [[15.0, 15.0]],
            "vision_range": 3.5,
        }
    )
    client.patch(f"/squads/{squad_id}/scenario", json={"guards": guards})

    captured: list[ScenarioConfig] = []

    async def fake_stream(_gw, _sid, scenario, **kwargs):
        captured.append(scenario)
        return {
            "directives": 1,
            "replans": 0,
            "mission": "active",
            "ticks_run": 2,
            "finished": False,
            "reason": "",
        }

    with patch(
        "gateway.simulation_runner.stream_simulation",
        new_callable=AsyncMock,
    ) as mock_stream:
        mock_stream.side_effect = fake_stream
        client.post(f"/squads/{squad_id}/simulate", json={"ticks": 2, "hz": 40})

        end = time.monotonic() + 5.0
        while time.monotonic() < end:
            status = client.get(f"/squads/{squad_id}/simulation").json()["simulation"]
            if status["status"] != "running":
                break
            time.sleep(0.02)

    assert len(captured) == 1
    sim = build_sim(captured[0])
    assert len(sim.guards) == 2


def test_resolve_scenario_for_squad_prefers_inline_edits() -> None:
    base = resolve_scenario_for_squad(
        scenario_raw=None,
        scenario_file="default",
    )
    edited = dict(base.raw)
    edited["guards"] = edited["guards"] + [
        {"id": "g9", "position": [1, 1], "patrol": [[1, 1]]},
    ]
    resolved = resolve_scenario_for_squad(
        scenario_raw=edited,
        scenario_file="default",
    )
    assert len(resolved.raw["guards"]) == 2


def test_reset_scenario_to_file(client: TestClient) -> None:
    squad_id = client.post("/squads/from-scenario", json={"scenario": "default"}).json()[
        "squad_id"
    ]
    scenario = client.get(f"/squads/{squad_id}/scenario").json()["scenario"]
    guards = list(scenario["guards"])
    guards.append({"id": "g2", "position": [1, 1], "patrol": [[1, 1]]})
    client.patch(f"/squads/{squad_id}/scenario", json={"guards": guards})
    client.patch(f"/squads/{squad_id}/scenario", json={"reset_to_file": True})
    saved = client.get(f"/squads/{squad_id}/scenario").json()["scenario"]
    assert len(saved["guards"]) == 1


def test_delete_squad(client: TestClient) -> None:
    squad_id = client.post("/squads/from-scenario", json={"scenario": "default"}).json()[
        "squad_id"
    ]
    deleted = client.delete(f"/squads/{squad_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert client.get(f"/squads/{squad_id}").status_code == 404
