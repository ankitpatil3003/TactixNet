"""Demo driver: streams a scenario through the live gateway at a fixed tick rate."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import websockets
import yaml

from contracts import RoleEnum
from simulation.grid import GridSim, Guard, SquadAgent
from simulation.movement import step_agent_by_role

DEFAULT_SCENARIO = Path(__file__).parent / "scenarios" / "default.yaml"


def load_scenario(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_sim(scenario: dict[str, Any]) -> GridSim:
    agents = [
        SquadAgent(agent_id=a["id"], position=(float(a["position"][0]), float(a["position"][1])))
        for a in scenario["agents"]
    ]
    guards = [
        Guard(
            guard_id=g["id"],
            position=(float(g["position"][0]), float(g["position"][1])),
            patrol_route=[(float(p[0]), float(p[1])) for p in g.get("patrol", [])],
        )
        for g in scenario["guards"]
    ]
    return GridSim(agents=agents, guards=guards)


def world_snapshot(sim: GridSim) -> dict[str, Any]:
    frames = sim.all_perceptions()
    alert_by_agent = {f.agent_id: f.alert_level.value for f in frames}
    return {
        "type": "world_snapshot",
        "tick": sim.tick,
        "agents": [
            {
                "id": a.agent_id,
                "position": list(a.position),
                "alert_level": alert_by_agent.get(a.agent_id, "CALM"),
            }
            for a in sim.agents
        ],
        "guards": [
            {
                "id": g.guard_id,
                "position": list(g.position),
                "vision_range": g.vision_range,
                "state": g.state,
            }
            for g in sim.guards
        ],
    }


async def run_demo(
    gateway: str,
    scenario_path: Path,
    hz: float,
    ticks: int,
    squad_index: int = 0,
) -> dict[str, int]:
    scenario = load_scenario(scenario_path)
    sim = build_sim(scenario)
    objective = tuple(scenario.get("objective_position", [16, 16]))
    roles: dict[str, RoleEnum] = {}

    async with httpx.AsyncClient(base_url=gateway) as http:
        response = await http.post(
            "/squads", json={"agent_ids": [a.agent_id for a in sim.agents]}
        )
        response.raise_for_status()
        squad_id = response.json()["squad_id"]

    ws_url = gateway.replace("http://", "ws://").replace("https://", "wss://")
    stats = {"directives": 0, "replans": 0}

    prefix = f"[squad-{squad_index}] " if squad_index else ""
    print(f"{prefix}Squad {squad_id} created — streaming {ticks} ticks at {hz}Hz")
    print(f"{prefix}Viewer: {gateway}/viewer?squad={squad_id}")

    async with websockets.connect(f"{ws_url}/ws/squads/{squad_id}") as ws:

        async def receiver() -> None:
            async for raw in ws:
                message = json.loads(raw)
                if message.get("type") == "directive":
                    stats["directives"] += 1
                    directive = message["directive"]
                    for award in directive["awards"]:
                        roles[award["agent_id"]] = RoleEnum(award["role"])
                    role_map = {a["agent_id"]: a["role"] for a in directive["awards"]}
                    flag = " [REPLAN]" if message.get("interrupted") else ""
                    if message.get("interrupted"):
                        stats["replans"] += 1
                    recovery = (
                        f" recovery={message['recovery_ms']}ms"
                        if message.get("recovery_ms") is not None
                        else ""
                    )
                    print(
                        f"{prefix}tick={directive['tick']} seq={directive['directive_seq']} "
                        f"latency={message['latency_ms']}ms roles={role_map}{flag}{recovery}"
                    )

        receive_task = asyncio.create_task(receiver())
        interval = 1.0 / hz

        try:
            for _ in range(ticks):
                sim.advance_tick()
                for agent in sim.agents:
                    role = roles.get(agent.agent_id, RoleEnum.BREACH)
                    step_agent_by_role(sim, agent, role, objective)
                await ws.send(json.dumps(world_snapshot(sim)))
                for frame in sim.all_perceptions():
                    await ws.send(frame.model_dump_json())
                await asyncio.sleep(interval)
        finally:
            receive_task.cancel()

    print(f"{prefix}Done: {stats['directives']} directives, {stats['replans']} replans")
    return stats


async def run_multi_demo(
    gateway: str,
    scenario_path: Path,
    hz: float,
    ticks: int,
    squads: int,
) -> None:
    await asyncio.gather(
        *[
            run_demo(gateway, scenario_path, hz, ticks, squad_index=i + 1)
            for i in range(squads)
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="TactixNet demo driver")
    parser.add_argument("--gateway", default="http://localhost:8000")
    parser.add_argument("--scenario", type=Path, default=DEFAULT_SCENARIO)
    parser.add_argument("--hz", type=float, default=10.0)
    parser.add_argument("--ticks", type=int, default=300)
    parser.add_argument("--squads", type=int, default=1, help="Number of concurrent squads")
    args = parser.parse_args()

    if args.squads > 1:
        asyncio.run(run_multi_demo(args.gateway, args.scenario, args.hz, args.ticks, args.squads))
    else:
        asyncio.run(run_demo(args.gateway, args.scenario, args.hz, args.ticks))


if __name__ == "__main__":
    main()
