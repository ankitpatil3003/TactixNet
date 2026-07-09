"""Reusable simulation streaming for an existing squad session."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from client import SquadClient
from contracts import AlertLevel, RoleEnum
from simulation.grid import GridSim, Guard, SquadAgent
from simulation.mission import MissionTracker, evaluate_mission, mission_snapshot
from simulation.movement import step_agent_by_role
from simulation.scenario import ScenarioConfig, load_scenario

SCENARIOS_DIR = Path(__file__).parent / "scenarios"


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


def world_snapshot(
    sim: GridSim,
    scenario: ScenarioConfig,
    tracker: MissionTracker,
    *,
    alert_by_agent: dict[str, AlertLevel] | None = None,
) -> dict[str, Any]:
    frames = sim.all_perceptions()
    alerts = alert_by_agent or {f.agent_id: f.alert_level for f in frames}
    return {
        "type": "world_snapshot",
        "tick": sim.tick,
        "agents": [
            {
                "id": a.agent_id,
                "position": list(a.position),
                "alert_level": alerts.get(a.agent_id, AlertLevel.CALM).value,
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
        "mission": mission_snapshot(scenario, tracker, sim, alert_by_agent=alerts),
    }


def list_scenario_files() -> list[Path]:
    return sorted(SCENARIOS_DIR.glob("*.yaml"))


def scenario_name_from_path(path: Path) -> str:
    return path.stem


def resolve_scenario(name_or_path: str) -> ScenarioConfig:
    candidate = Path(name_or_path)
    if candidate.suffix == ".yaml" and candidate.exists():
        return load_scenario(candidate)
    yaml_path = SCENARIOS_DIR / f"{name_or_path}.yaml"
    if not yaml_path.exists():
        raise FileNotFoundError(f"Scenario not found: {name_or_path}")
    return load_scenario(yaml_path)


def scenario_summary(config: ScenarioConfig, *, file_name: str) -> dict[str, Any]:
    return {
        "name": file_name,
        "display_name": config.name,
        "tick_rate_hz": config.tick_rate_hz,
        "squad_size": config.squad_size,
        "objective": config.objective,
        "win_condition": config.win_condition,
        "agent_ids": [a["id"] for a in config.raw.get("agents", [])],
    }


async def stream_simulation(
    gateway: str,
    squad_id: str,
    scenario: ScenarioConfig,
    *,
    ticks: int,
    hz: float | None = None,
    cancel_event: asyncio.Event | None = None,
    on_tick: Any | None = None,
) -> dict[str, Any]:
    """Stream perception frames for an existing squad (does not create the squad)."""
    effective_hz = hz if hz is not None else scenario.tick_rate_hz
    sim = build_sim(scenario)
    objective = scenario.objective_position
    roles: dict[str, RoleEnum] = {}
    tracker = MissionTracker()
    stats: dict[str, Any] = {
        "directives": 0,
        "replans": 0,
        "mission": "active",
        "ticks_run": 0,
        "squad_id": squad_id,
    }

    client = SquadClient(gateway, squad_id=squad_id)
    await client.connect()

    async def receiver() -> None:
        while True:
            message = await client.receive_json()
            if message.get("type") != "directive":
                continue
            stats["directives"] += 1
            directive = message["directive"]
            if directive["awards"]:
                for award in directive["awards"]:
                    roles[award["agent_id"]] = RoleEnum(award["role"])
            if message.get("interrupted"):
                stats["replans"] += 1

    receive_task = asyncio.create_task(receiver())
    interval = 1.0 / effective_hz

    try:
        for _tick_num in range(1, ticks + 1):
            if cancel_event is not None and cancel_event.is_set():
                stats["mission"] = "cancelled"
                break

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
            evaluate_mission(sim, scenario, tracker, alert_by_agent=alert_by_agent)
            stats["mission"] = tracker.status
            stats["ticks_run"] = sim.tick

            snapshot = world_snapshot(sim, scenario, tracker, alert_by_agent=alert_by_agent)
            await client.send_snapshot(snapshot)
            for frame in sim.all_perceptions():
                await client.send_frame(frame)

            if on_tick is not None:
                await on_tick(sim.tick, tracker.status, snapshot)

            if tracker.is_finished():
                break

            await asyncio.sleep(interval)
    finally:
        receive_task.cancel()
        try:
            await receive_task
        except asyncio.CancelledError:
            pass
        await client.aclose()

    stats["finished"] = tracker.is_finished()
    stats["reason"] = tracker.reason
    return stats
