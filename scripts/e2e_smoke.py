"""Manual E2E smoke — run against a live gateway on :8000.

Covers: health, console endpoints (scenarios/list/create-from-scenario),
doctrine, live streaming, mission tracking, and replay events.
"""

from __future__ import annotations

import asyncio
import sys

import httpx

from client import SquadClient
from contracts import AlertLevel, DoctrineUpdate, RoleEnum
from simulation.driver import build_sim, resolve_scenario, world_snapshot
from simulation.mission import MissionTracker, evaluate_mission
from simulation.movement import step_agent_by_role
from simulation.run_demo import DEFAULT_SCENARIO

GATEWAY = "http://127.0.0.1:8000"
SCENARIOS = [
    DEFAULT_SCENARIO,
    DEFAULT_SCENARIO.parent / "ambush.yaml",
    DEFAULT_SCENARIO.parent / "hold.yaml",
]


async def check_health() -> None:
    async with httpx.AsyncClient() as http:
        r = await http.get(f"{GATEWAY}/health", timeout=5.0)
        r.raise_for_status()
        body = r.json()
        assert body["status"] == "ok"
        print(f"[health] ok event_log={body['event_log']} session_store={body['session_store']}")


async def check_console_endpoints() -> None:
    async with httpx.AsyncClient(base_url=GATEWAY, timeout=10.0) as http:
        scenarios = (await http.get("/scenarios")).json()
        assert scenarios["total"] >= 1
        print(f"[console] scenarios={scenarios['total']}")

        created = await http.post("/squads/from-scenario", json={"scenario": "default"})
        created.raise_for_status()
        squad_id = created.json()["squad_id"]

        squads = (await http.get("/squads")).json()
        assert any(s["squad_id"] == squad_id for s in squads["squads"])
        print(f"[console] created idle squad {squad_id[:8]}… listed={squads['total']}")

        sim = (await http.get(f"/squads/{squad_id}/simulation")).json()
        assert sim["simulation"]["status"] == "idle"
        print("[console] simulation status idle before start — ok")


async def run_scenario_demo(path) -> str:
    scenario = resolve_scenario(str(path))
    sim = build_sim(scenario)
    objective = scenario.objective_position
    roles: dict[str, RoleEnum] = {}
    tracker = MissionTracker()

    squad = await SquadClient.create(
        GATEWAY,
        [a.agent_id for a in sim.agents],
        objective_ref=scenario.objective,
        scenario=scenario.raw,
    )
    assert squad.squad_id
    await squad.connect()

    meta = await squad.get_scenario()
    assert meta["scenario"]["name"] == scenario.name
    print(
        f"[scenario:{scenario.name}] squad={squad.squad_id[:8]}… "
        f"objective={scenario.objective}"
    )

    directives = 0
    for _tick in range(1, 31):
        sim.advance_tick()
        frames = sim.all_perceptions()
        alert_by_agent = {f.agent_id: f.alert_level for f in frames}
        for agent in sim.agents:
            role = roles.get(agent.agent_id, RoleEnum.BREACH)
            step_agent_by_role(
                sim,
                agent,
                role,
                objective,
                alert_level=alert_by_agent.get(agent.agent_id, AlertLevel.CALM),
            )
        evaluate_mission(sim, scenario, tracker, alert_by_agent=alert_by_agent)
        await squad.send_snapshot(
            world_snapshot(sim, scenario, tracker, alert_by_agent=alert_by_agent)
        )
        for frame in sim.all_perceptions():
            await squad.send_frame(frame)
        try:
            msg = await asyncio.wait_for(squad.receive_json(), timeout=2.0)
            if msg.get("type") == "directive":
                directives += 1
                for award in msg["directive"]["awards"]:
                    roles[award["agent_id"]] = RoleEnum(award["role"])
        except TimeoutError:
            pass

    async with httpx.AsyncClient() as http:
        events = await http.get(
            f"{GATEWAY}/squads/{squad.squad_id}/events?replay_only=true&count=10000"
        )
    events.raise_for_status()
    replay = events.json()
    assert replay["total"] >= directives, (
        f"expected events >= {directives}, got {replay['total']}"
    )
    print(f"[scenario:{scenario.name}] directives={directives} replay_frames={replay['total']}")

    doctrine = DoctrineUpdate(
        squad_id=squad.squad_id,
        role_weights={RoleEnum.DISTRACT: 2.5},
        priority_objective=scenario.objective,
    )
    state = await squad.apply_doctrine(doctrine)
    assert state["doctrine"]["priority_objective"] == scenario.objective
    print(f"[scenario:{scenario.name}] doctrine applied ok")

    await squad.aclose()
    return squad.squad_id


async def main() -> None:
    await check_health()
    await check_console_endpoints()
    squad_ids = []
    for path in SCENARIOS:
        squad_ids.append(await run_scenario_demo(path))
    print(f"[done] E2E smoke passed for {len(squad_ids)} scenarios")
    for sid in squad_ids:
        print(f"  viewer: {GATEWAY}/viewer?squad={sid}")
        print(f"  replay: {GATEWAY}/viewer?squad={sid}&replay=1")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        raise
