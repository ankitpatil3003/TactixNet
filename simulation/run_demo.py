"""Demo driver: streams a scenario through the live gateway at a fixed tick rate.

Usage:
    python -m simulation.run_demo --hz 10 --ticks 300
    python -m simulation.run_demo --gateway http://localhost:8000 \
        --scenario simulation/scenarios/default.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import websockets
import yaml

from simulation.grid import GridSim, Guard, SquadAgent

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


def step_agents_toward(
    sim: GridSim, target: tuple[float, float], step: float = 0.2
) -> None:
    """Move every squad agent one step toward the objective."""
    for agent in sim.agents:
        dx = target[0] - agent.position[0]
        dy = target[1] - agent.position[1]
        dist = (dx * dx + dy * dy) ** 0.5
        if dist < step:
            agent.position = target
            continue
        agent.position = (
            agent.position[0] + dx / dist * step,
            agent.position[1] + dy / dist * step,
        )


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
            }
            for g in sim.guards
        ],
    }


async def run_demo(
    gateway: str,
    scenario_path: Path,
    hz: float,
    ticks: int,
) -> dict[str, int]:
    scenario = load_scenario(scenario_path)
    sim = build_sim(scenario)
    objective = tuple(scenario.get("objective_position", [16, 16]))

    async with httpx.AsyncClient(base_url=gateway) as http:
        response = await http.post(
            "/squads", json={"agent_ids": [a.agent_id for a in sim.agents]}
        )
        response.raise_for_status()
        squad_id = response.json()["squad_id"]

    ws_url = gateway.replace("http://", "ws://").replace("https://", "wss://")
    stats = {"directives": 0, "replans": 0}

    print(f"Squad {squad_id} created — streaming {ticks} ticks at {hz}Hz")
    print(f"Viewer: {gateway}/viewer?squad={squad_id}")

    async with websockets.connect(f"{ws_url}/ws/squads/{squad_id}") as ws:

        async def receiver() -> None:
            async for raw in ws:
                message = json.loads(raw)
                if message.get("type") == "directive":
                    stats["directives"] += 1
                    directive = message["directive"]
                    roles = {a["agent_id"]: a["role"] for a in directive["awards"]}
                    flag = " [REPLAN]" if message.get("interrupted") else ""
                    if message.get("interrupted"):
                        stats["replans"] += 1
                    print(
                        f"tick={directive['tick']} seq={directive['directive_seq']} "
                        f"latency={message['latency_ms']}ms roles={roles}{flag}"
                    )

        receive_task = asyncio.create_task(receiver())
        interval = 1.0 / hz

        try:
            for _ in range(ticks):
                sim.advance_tick()
                step_agents_toward(sim, objective)
                await ws.send(json.dumps(world_snapshot(sim)))
                for frame in sim.all_perceptions():
                    await ws.send(frame.model_dump_json())
                await asyncio.sleep(interval)
        finally:
            receive_task.cancel()

    print(f"Done: {stats['directives']} directives, {stats['replans']} replans")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="TactixNet demo driver")
    parser.add_argument("--gateway", default="http://localhost:8000")
    parser.add_argument("--scenario", type=Path, default=DEFAULT_SCENARIO)
    parser.add_argument("--hz", type=float, default=10.0)
    parser.add_argument("--ticks", type=int, default=300)
    args = parser.parse_args()

    asyncio.run(run_demo(args.gateway, args.scenario, args.hz, args.ticks))


if __name__ == "__main__":
    main()
