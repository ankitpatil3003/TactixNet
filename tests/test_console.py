"""Tests for squad console control plane endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from contracts import RoleEnum
from gateway import app as app_module
from gateway.app import app
from gateway.simulation_runner import SimulationRunner


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        app_module._simulation_runner = SimulationRunner("http://testserver")
        yield test_client
        runner = app_module._simulation_runner
        if runner is not None:
            for state in runner._states.values():
                if state.status == "running":
                    test_client.post(f"/squads/{state.squad_id}/simulate/cancel")


def test_console_served(client: TestClient) -> None:
    response = client.get("/console")
    assert response.status_code == 200
    assert "TactixNet Console" in response.text


def test_list_scenarios(client: TestClient) -> None:
    response = client.get("/scenarios")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    names = {s["name"] for s in body["scenarios"]}
    assert "default" in names


def test_list_squads_empty_initially(client: TestClient) -> None:
    response = client.get("/squads")
    assert response.status_code == 200
    assert isinstance(response.json()["squads"], list)


def test_create_squad_from_scenario(client: TestClient) -> None:
    response = client.post("/squads/from-scenario", json={"scenario": "default"})
    assert response.status_code == 200
    body = response.json()
    assert len(body["agent_ids"]) == 5
    assert body["objective_ref"] == "breach-gate"

    listed = client.get("/squads").json()
    ids = {s["squad_id"] for s in listed["squads"]}
    assert body["squad_id"] in ids


def test_simulate_requires_existing_squad(client: TestClient) -> None:
    response = client.post(
        "/squads/missing/simulate",
        json={"scenario": "default", "ticks": 5},
    )
    assert response.status_code == 404


def test_simulate_starts_background_task(client: TestClient) -> None:
    create = client.post("/squads/from-scenario", json={"scenario": "default"})
    squad_id = create.json()["squad_id"]

    target = "gateway.simulation_runner.stream_simulation"
    with patch(target, new_callable=AsyncMock) as mock_stream:
        mock_stream.return_value = {
            "directives": 3,
            "replans": 1,
            "mission": "won",
            "ticks_run": 5,
            "finished": True,
            "reason": "3 agent(s) reached objective",
        }
        start = client.post(f"/squads/{squad_id}/simulate", json={"ticks": 5})
        assert start.status_code == 200
        assert start.json()["started"] is True

    status = client.get(f"/squads/{squad_id}/simulation")
    assert status.status_code == 200
    sim_state = status.json()["simulation"]
    assert sim_state["status"] in {"running", "finished", "error"}
    if sim_state["status"] == "finished":
        assert sim_state["directives"] == 3
        assert sim_state["reason"] == "3 agent(s) reached objective"


def test_doctrine_before_simulate_flow(client: TestClient) -> None:
    create = client.post("/squads/from-scenario", json={"scenario": "default"})
    squad_id = create.json()["squad_id"]

    doctrine = {
        "squad_id": squad_id,
        "role_weights": {RoleEnum.DISTRACT.value: 5.0, RoleEnum.FLANK.value: 0.1},
        "priority_objective": "breach-gate",
    }
    applied = client.post(f"/squads/{squad_id}/doctrine", json=doctrine)
    assert applied.status_code == 200
    assert applied.json()["doctrine"] is not None

    listed = client.get("/squads").json()
    row = next(s for s in listed["squads"] if s["squad_id"] == squad_id)
    assert row["has_doctrine"] is True
