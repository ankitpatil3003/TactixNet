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
