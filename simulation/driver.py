"""Reusable simulation streaming for an existing squad session."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from client import SquadClient
from contracts import AlertLevel, RoleEnum
from simulation.doctrine_bridge import (
    DoctrineState,
    movement_step_scale,
    should_hold_agents,
    should_retreat_agents,
    step_retreat,
)
from simulation.grid import GridSim, Guard, SquadAgent
from simulation.mission import MissionTracker, evaluate_mission, mission_snapshot
from simulation.movement import step_agent_by_role
from simulation.scenario import ScenarioConfig, load_scenario

SCENARIOS_DIR = Path(__file__).parent / "scenarios"


def build_sim(scenario: ScenarioConfig) -> GridSim:
    data = scenario.raw
    grid_size = int(data.get("grid_size", 20))
    agents = [
        SquadAgent(agent_id=a["id"], position=(float(a["position"][0]), float(a["position"][1])))
        for a in data["agents"]
    ]
    guards = [
        Guard(
            guard_id=g["id"],
            position=(float(g["position"][0]), float(g["position"][1])),
            patrol_route=[(float(p[0]), float(p[1])) for p in g.get("patrol", [])],
            vision_range=float(g.get("vision_range", 3.5)),
            vision_angle_deg=float(g.get("vision_angle_deg", 120.0)),
            patrol_speed=float(g.get("patrol_speed", 0.2)),
        )
        for g in data["guards"]
    ]
    return GridSim(width=grid_size, height=grid_size, agents=agents, guards=guards)


def world_snapshot(
    sim: GridSim,
    scenario: ScenarioConfig,
    tracker: MissionTracker,
    *,
    alert_by_agent: dict[str, AlertLevel] | None = None,
    doctrine_state: DoctrineState | None = None,
) -> dict[str, Any]:
    frames = sim.all_perceptions()
    alerts = alert_by_agent or {f.agent_id: f.alert_level for f in frames}
    objective = doctrine_state.objective if doctrine_state else scenario.objective_position
    doctrine_payload = doctrine_state.to_snapshot() if doctrine_state else None
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
                "vision_angle_deg": g.vision_angle_deg,
                "heading": g.heading,
                "state": g.state,
                "patrol": [list(p) for p in g.patrol_route],
            }
            for g in sim.guards
        ],
        "mission": mission_snapshot(
            scenario,
            tracker,
            sim,
            alert_by_agent=alerts,
            objective_position=objective,
            doctrine=doctrine_payload,
        ),
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
        "guard_count": len(config.raw.get("guards", [])),
        "grid_size": int(config.raw.get("grid_size", 20)),
        "agent_ids": [a["id"] for a in config.raw.get("agents", [])],
    }


def resolve_scenario_for_squad(
    *,
    scenario_raw: dict[str, Any] | None,
    scenario_file: str | None,
    override_name: str | None = None,
) -> ScenarioConfig:
    """Prefer inline squad scenario edits; fall back to YAML on disk."""
    if scenario_raw is not None:
        if override_name is None or override_name == scenario_file:
            return ScenarioConfig.from_dict(scenario_raw)
    file_name = override_name or scenario_file
    if file_name is None:
        raise FileNotFoundError("No scenario configured for squad")
    return resolve_scenario(file_name)


async def stream_simulation(
    gateway: str,
    squad_id: str,
    scenario: ScenarioConfig,
    *,
    ticks: int,
    hz: float | None = None,
    cancel_event: asyncio.Event | None = None,
    on_tick: Any | None = None,
    initial_doctrine: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Stream perception frames for an existing squad (does not create the squad)."""
    effective_hz = hz if hz is not None else scenario.tick_rate_hz
    sim = build_sim(scenario)
    doctrine_state = DoctrineState.from_doctrine(initial_doctrine, scenario)
    objective = doctrine_state.objective
    spawn_roles = scenario.raw.get("spawn_roles", {})
    roles = {aid: RoleEnum(role) for aid, role in spawn_roles.items()}
    default_role = RoleEnum.STEALTH_COVER
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
            msg_type = message.get("type")
            if msg_type == "doctrine":
                doctrine_state.update_from_doctrine(message.get("doctrine", {}), scenario)
                continue
            if msg_type != "directive":
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
            objective = doctrine_state.objective
            fallback = doctrine_state.fallback_plan

            if should_hold_agents(fallback):
                pass
            elif should_retreat_agents(fallback):
                for agent in sim.agents:
                    step_retreat(sim, agent, objective=objective)
            else:
                for agent in sim.agents:
                    role = roles.get(agent.agent_id, default_role)
                    scale = movement_step_scale(role, doctrine_state.role_weights)
                    step_agent_by_role(
                        sim,
                        agent,
                        role,
                        objective,
                        alert_level=alert_by_agent.get(agent.agent_id, AlertLevel.CALM),
                        step_scale=scale,
                    )
            evaluate_mission(
                sim,
                scenario,
                tracker,
                alert_by_agent=alert_by_agent,
                objective_position=objective,
            )
            stats["mission"] = tracker.status
            stats["ticks_run"] = sim.tick

            snapshot = world_snapshot(
                sim,
                scenario,
                tracker,
                alert_by_agent=alert_by_agent,
                doctrine_state=doctrine_state,
            )
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
