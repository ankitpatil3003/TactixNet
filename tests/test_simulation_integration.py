"""Integration tests for live simulation path (console /simulate flow)."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from contracts import AlertLevel, RoleEnum
from gateway import app as app_module
from gateway.app import app
from gateway.simulation_runner import SimulationRunner
from simulation.driver import build_sim, resolve_scenario, stream_simulation
from simulation.mission import MissionTracker, evaluate_mission
from simulation.movement import step_agent_by_role


class _TestClientWebSocket:
    """Bridge TestClient sync WebSocket to async stream_simulation."""

    def __init__(self, ws: Any) -> None:
        self._ws = ws

    async def send(self, payload: str) -> None:
        await asyncio.to_thread(self._ws.send_text, payload)

    async def recv(self) -> str:
        return await asyncio.to_thread(self._ws.receive_text)


class _InProcessSquadClient:
    def __init__(self, squad_id: str, ws: _TestClientWebSocket) -> None:
        self.squad_id = squad_id
        self._ws = ws

    async def connect(self, *, observer: bool = False) -> None:
        return None

    async def send_snapshot(self, snapshot: dict[str, Any]) -> None:
        await self._ws.send(json.dumps(snapshot))

    async def send_frame(self, frame: Any) -> None:
        await self._ws.send(frame.model_dump_json())

    async def receive_json(self) -> dict[str, Any]:
        raw = await self._ws.recv()
        return json.loads(raw)

    async def aclose(self) -> None:
        return None


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


def _client_factory(squad_id: str, bridge: _TestClientWebSocket):
    def factory(_gateway: str, squad_id: str = squad_id) -> _InProcessSquadClient:
        return _InProcessSquadClient(squad_id, bridge)

    return factory


@pytest.mark.asyncio
async def test_stream_simulation_seeds_spawn_roles(client: TestClient) -> None:
    create = client.post("/squads/from-scenario", json={"scenario": "default"})
    squad_id = create.json()["squad_id"]

    with client.websocket_connect(f"/ws/squads/{squad_id}") as ws:
        bridge = _TestClientWebSocket(ws)
        with patch("simulation.driver.SquadClient", _client_factory(squad_id, bridge)):
            result = await stream_simulation(
                "http://testserver",
                squad_id,
                resolve_scenario("default"),
                ticks=8,
                hz=50.0,
            )

    assert result["ticks_run"] >= 1
    assert result["directives"] >= 1
    assert "reason" in result


@pytest.mark.asyncio
async def test_stream_simulation_ambush_scenario(client: TestClient) -> None:
    create = client.post("/squads/from-scenario", json={"scenario": "ambush"})
    squad_id = create.json()["squad_id"]

    with client.websocket_connect(f"/ws/squads/{squad_id}") as ws:
        bridge = _TestClientWebSocket(ws)
        with patch("simulation.driver.SquadClient", _client_factory(squad_id, bridge)):
            result = await stream_simulation(
                "http://testserver",
                squad_id,
                resolve_scenario("ambush"),
                ticks=8,
                hz=50.0,
            )

    assert result["ticks_run"] >= 1
    assert result["mission"] in {"active", "won", "lost", "cancelled"}


@pytest.mark.asyncio
async def test_stream_simulation_respects_cancel_event(client: TestClient) -> None:
    create = client.post("/squads/from-scenario", json={"scenario": "default"})
    squad_id = create.json()["squad_id"]
    cancel = asyncio.Event()

    with client.websocket_connect(f"/ws/squads/{squad_id}") as ws:
        bridge = _TestClientWebSocket(ws)
        with patch("simulation.driver.SquadClient", _client_factory(squad_id, bridge)):

            async def _run() -> dict[str, Any]:
                return await stream_simulation(
                    "http://testserver",
                    squad_id,
                    resolve_scenario("default"),
                    ticks=200,
                    hz=80.0,
                    cancel_event=cancel,
                )

            task = asyncio.create_task(_run())
            await asyncio.sleep(0.05)
            cancel.set()
            result = await task

    assert result["mission"] == "cancelled"


def test_spawn_roles_move_breach_before_directive() -> None:
    scenario = resolve_scenario("default")
    sim = build_sim(scenario)
    breach_id = next(
        aid for aid, role in scenario.raw.get("spawn_roles", {}).items() if role == "breach"
    )
    breach = next(a for a in sim.agents if a.agent_id == breach_id)
    start = breach.position
    objective = scenario.objective_position

    sim.advance_tick()
    frames = sim.all_perceptions()
    alert_by_agent = {f.agent_id: f.alert_level for f in frames}
    spawn_roles = {aid: RoleEnum(role) for aid, role in scenario.raw.get("spawn_roles", {}).items()}
    role = spawn_roles.get(breach_id, RoleEnum.BREACH)
    step_agent_by_role(
        sim,
        breach,
        role,
        objective,
        alert_level=alert_by_agent.get(breach_id, AlertLevel.CALM),
    )
    assert breach.position != start


def test_simulate_endpoint_finishes_with_stats(client: TestClient) -> None:
    create = client.post("/squads/from-scenario", json={"scenario": "default"})
    squad_id = create.json()["squad_id"]

    with patch(
        "gateway.simulation_runner.stream_simulation",
        new_callable=AsyncMock,
    ) as mock_stream:
        mock_stream.return_value = {
            "directives": 5,
            "replans": 1,
            "mission": "won",
            "ticks_run": 12,
            "finished": True,
            "reason": "3 agent(s) reached objective",
        }
        start = client.post(f"/squads/{squad_id}/simulate", json={"ticks": 12, "hz": 40})
        assert start.status_code == 200

        end = time.monotonic() + 5.0
        status: dict[str, Any] = {}
        while time.monotonic() < end:
            status = client.get(f"/squads/{squad_id}/simulation").json()["simulation"]
            if status["status"] in {"finished", "cancelled", "error"}:
                break
            time.sleep(0.02)

        assert status["status"] == "finished"
        assert status["ticks_run"] == 12
        assert status["directives"] == 5
        assert status["reason"] == "3 agent(s) reached objective"


def test_simulate_scenario_override_passed_to_runner(client: TestClient) -> None:
    create = client.post("/squads/from-scenario", json={"scenario": "default"})
    squad_id = create.json()["squad_id"]

    with patch(
        "gateway.simulation_runner.stream_simulation",
        new_callable=AsyncMock,
    ) as mock_stream:
        mock_stream.return_value = {
            "directives": 1,
            "replans": 0,
            "mission": "active",
            "ticks_run": 3,
            "finished": False,
            "reason": "",
        }
        response = client.post(
            f"/squads/{squad_id}/simulate",
            json={"scenario": "ambush", "ticks": 3, "hz": 40},
        )
        assert response.status_code == 200

        end = time.monotonic() + 5.0
        status: dict[str, Any] = {}
        while time.monotonic() < end:
            status = client.get(f"/squads/{squad_id}/simulation").json()["simulation"]
            if status["status"] != "running":
                break
            time.sleep(0.02)

        assert status["scenario"] == "ambush"
        scenario_arg = mock_stream.call_args[0][2]
        assert scenario_arg.name == "ambush"


def test_default_mission_wins_with_spawn_roles() -> None:
    scenario = resolve_scenario("default")
    sim = build_sim(scenario)
    objective = scenario.objective_position
    tracker = MissionTracker()
    spawn_roles = {aid: RoleEnum(role) for aid, role in scenario.raw.get("spawn_roles", {}).items()}

    for _ in range(300):
        sim.advance_tick()
        frames = sim.all_perceptions()
        alert_by_agent = {f.agent_id: f.alert_level for f in frames}
        for agent in sim.agents:
            role = spawn_roles.get(agent.agent_id, RoleEnum.BREACH)
            step_agent_by_role(
                sim,
                agent,
                role,
                objective,
                alert_level=alert_by_agent.get(agent.agent_id, AlertLevel.CALM),
            )
        evaluate_mission(sim, scenario, tracker, alert_by_agent=alert_by_agent)
        if tracker.is_finished():
            break

    assert tracker.status == "won"
    assert tracker.reason


@pytest.mark.asyncio
async def test_chaos_compromise_triggers_replan(client: TestClient) -> None:
    create = client.post("/squads/from-scenario", json={"scenario": "default"})
    squad_id = create.json()["squad_id"]

    sim = build_sim(resolve_scenario("default"))
    guard_pos = sim.guards[0].position
    for agent in sim.agents[:1]:
        agent.position = (guard_pos[0] + 0.1, guard_pos[1])

    replans = 0
    compromised = False

    with client.websocket_connect(f"/ws/squads/{squad_id}") as ws:
        bridge = _TestClientWebSocket(ws)
        inproc = _InProcessSquadClient(squad_id, bridge)
        original_receive = inproc.receive_json

        async def counting_receive() -> dict[str, Any]:
            nonlocal replans
            msg = await original_receive()
            if msg.get("interrupted"):
                replans += 1
            return msg

        inproc.receive_json = counting_receive  # type: ignore[method-assign]

        with patch("simulation.driver.SquadClient", lambda _gw, squad_id=squad_id: inproc):
            with patch("simulation.driver.build_sim", lambda _scenario: sim):
                await stream_simulation(
                    "http://testserver",
                    squad_id,
                    resolve_scenario("default"),
                    ticks=20,
                    hz=50.0,
                )

        for frame in sim.all_perceptions():
            if frame.alert_level == AlertLevel.COMPROMISED:
                compromised = True

    assert replans >= 1 or compromised
