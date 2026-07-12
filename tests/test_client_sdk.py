import httpx
import pytest
from httpx import ASGITransport

from client import SquadClient
from contracts import DoctrineUpdate, RoleEnum
from gateway.app import app


@pytest.mark.asyncio
async def test_squad_client_create_and_get_state() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
        squad = await SquadClient.create("http://testserver", ["a1"], http=http)
        state = await squad.get_state()
        assert state["agent_ids"] == ["a1"]
        assert state["squad_id"] == squad.squad_id
        await squad.aclose()


@pytest.mark.asyncio
async def test_squad_client_apply_doctrine() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
        squad = await SquadClient.create("http://testserver", ["a1"], http=http)

        doctrine = DoctrineUpdate(
            squad_id=squad.squad_id,
            role_weights={RoleEnum.DISTRACT: 3.0},
            priority_objective="breach-gate",
        )
        state = await squad.apply_doctrine(doctrine)
        assert state["doctrine"]["priority_objective"] == "breach-gate"
        await squad.aclose()


@pytest.mark.asyncio
async def test_squad_client_get_events() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
        squad = await SquadClient.create("http://testserver", ["a1"], http=http)
        events = await squad.get_events(count=10)
        assert events["squad_id"] == squad.squad_id
        assert "events" in events
        await squad.aclose()


@pytest.mark.asyncio
async def test_squad_client_with_scenario_metadata() -> None:
    transport = ASGITransport(app=app)
    scenario = {"name": "test", "objective": "obj-a", "tick_rate_hz": 12}
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
        squad = await SquadClient.create(
            "http://testserver",
            ["a1"],
            objective_ref="obj-a",
            scenario=scenario,
            http=http,
        )
        meta = await squad.get_scenario()
        assert meta["scenario"]["objective"] == "obj-a"
        await squad.aclose()


def test_apply_doctrine_syncs_objective_ref() -> None:
    from fastapi.testclient import TestClient

    from gateway import app as app_module
    from gateway.app import app
    from gateway.simulation_runner import SimulationRunner

    with TestClient(app) as test_client:
        app_module._simulation_runner = SimulationRunner("http://testserver")
        squad_id = test_client.post(
            "/squads/from-scenario",
            json={"scenario": "default"},
        ).json()["squad_id"]
        response = test_client.post(
            f"/squads/{squad_id}/doctrine",
            json={
                "squad_id": squad_id,
                "role_weights": {"breach": 2.0},
                "priority_objective": "flank-point",
                "fallback_plan": "hold-position",
            },
        )
        assert response.status_code == 200
        state = response.json()
        assert state["objective_ref"] == "flank-point"
        assert state["doctrine"]["fallback_plan"] == "hold-position"


@pytest.mark.asyncio
async def test_squad_client_control_plane_methods() -> None:
    from unittest.mock import AsyncMock, patch

    from gateway import app as app_module
    from gateway.simulation_runner import SimulationRunner

    app_module._simulation_runner = SimulationRunner("http://testserver")
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
        client = SquadClient("http://testserver")
        client._http = http
        health = await client.health()
        assert health["status"] == "ok"

        scenarios = await client.list_scenarios()
        assert scenarios["total"] >= 1

        squad = await SquadClient.create_from_scenario("http://testserver", "default", http=http)
        squads = await squad.list_squads()
        assert any(row["squad_id"] == squad.squad_id for row in squads["squads"])

        with patch(
            "gateway.simulation_runner.stream_simulation",
            new_callable=AsyncMock,
        ) as mock_stream:
            mock_stream.return_value = {
                "directives": 1,
                "replans": 0,
                "mission": "active",
                "ticks_run": 2,
                "finished": False,
                "reason": "",
            }
            started = await squad.start_simulation(ticks=2, hz=40)
            assert started["started"] is True

        status = await squad.get_simulation()
        assert status["simulation"]["status"] in {"running", "finished", "error"}

        await squad.cancel_simulation()
        deleted = await squad.delete_squad()
        assert deleted["deleted"] is True
        await squad.aclose()
