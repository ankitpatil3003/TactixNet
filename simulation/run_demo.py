"""Demo driver: streams a scenario through the live gateway at a fixed tick rate."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any

from client import SquadClient
from contracts import AlertLevel, RoleEnum
from simulation.grid import GridSim, Guard, SquadAgent
from simulation.movement import step_agent_by_role
from simulation.scenario import ScenarioConfig, load_scenario

DEFAULT_SCENARIO = Path(__file__).parent / "scenarios" / "default.yaml"


def build_sim(scenario: ScenarioConfig) -> GridSim:
    data = scenario.raw
    agents = [
        SquadAgent(agent_id=a["id"], position=(float(a["position"][0]), float(a["position"][1])))
        for a in data["agents"]
    ]
    guards = [
        Guard(
            guard_id=g["id"],
            position=(float(g["position"][0]), float(g["position"][1])),
            patrol_route=[(float(p[0]), float(p[1])) for p in g.get("patrol", [])],
        )
        for g in data["guards"]
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
    hz: float | None,
    ticks: int,
    squad_index: int = 0,
) -> dict[str, int]:
    scenario = load_scenario(scenario_path)
    effective_hz = hz if hz is not None else scenario.tick_rate_hz
    sim = build_sim(scenario)
    objective = scenario.objective_position
    roles: dict[str, RoleEnum] = {}

    client = await SquadClient.create(
        gateway,
        [a.agent_id for a in sim.agents],
        objective_ref=scenario.objective,
        scenario=scenario.raw,
    )
    squad_id = client.squad_id
    assert squad_id is not None

    stats = {"directives": 0, "replans": 0}
    prefix = f"[squad-{squad_index}] " if squad_index else ""
    print(f"{prefix}Squad {squad_id} created — streaming {ticks} ticks at {effective_hz}Hz")
    print(f"{prefix}Scenario: {scenario.name} -> {scenario.objective}")
    print(f"{prefix}Viewer: {gateway}/viewer?squad={squad_id}")

    await client.connect()

    async def receiver() -> None:
        while True:
            message = await client.receive_json()
            if message.get("type") == "directive":
                stats["directives"] += 1
                directive = message["directive"]
                if directive["awards"]:
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
    interval = 1.0 / effective_hz

    try:
        for _ in range(ticks):
            sim.advance_tick()
            frames = sim.all_perceptions()
            alert_by_agent = {f.agent_id: f.alert_level for f in frames}
            for agent in sim.agents:
                role = roles.get(agent.agent_id, RoleEnum.STEALTH_COVER)
                step_agent_by_role(
                    sim,
                    agent,
                    role,
                    objective,
                    alert_level=alert_by_agent.get(agent.agent_id, AlertLevel.CALM),
                )
            await client.send_snapshot(world_snapshot(sim))
            for frame in sim.all_perceptions():
                await client.send_frame(frame)
            await asyncio.sleep(interval)
    finally:
        receive_task.cancel()
        await client.aclose()

    print(f"{prefix}Done: {stats['directives']} directives, {stats['replans']} replans")
    return stats


async def run_multi_demo(
    gateway: str,
    scenario_path: Path,
    hz: float | None,
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
    parser.add_argument(
        "--hz",
        type=float,
        default=None,
        help="Tick rate (default: scenario tick_rate_hz)",
    )
    parser.add_argument("--ticks", type=int, default=300)
    parser.add_argument("--squads", type=int, default=1, help="Number of concurrent squads")
    args = parser.parse_args()

    if args.squads > 1:
        asyncio.run(run_multi_demo(args.gateway, args.scenario, args.hz, args.ticks, args.squads))
    else:
        asyncio.run(run_demo(args.gateway, args.scenario, args.hz, args.ticks))


if __name__ == "__main__":
    main()
