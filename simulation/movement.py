"""Role-based agent movement helpers for the living simulation."""

from __future__ import annotations

import math

from contracts import RoleEnum
from simulation.grid import GridSim, SquadAgent, _distance


def move_toward(
    position: tuple[float, float], target: tuple[float, float], step: float
) -> tuple[float, float]:
    dx = target[0] - position[0]
    dy = target[1] - position[1]
    dist = math.hypot(dx, dy)
    if dist < step:
        return target
    return (position[0] + dx / dist * step, position[1] + dy / dist * step)


def move_away(
    position: tuple[float, float], threat: tuple[float, float], step: float
) -> tuple[float, float]:
    dx = position[0] - threat[0]
    dy = position[1] - threat[1]
    dist = math.hypot(dx, dy)
    if dist < 1e-6:
        return (position[0] + step, position[1])
    return (position[0] + dx / dist * step, position[1] + dy / dist * step)


def nearest_guard(sim: GridSim, agent: SquadAgent) -> tuple[float, float] | None:
    if not sim.guards:
        return None
    return min(sim.guards, key=lambda g: _distance(agent.position, g.position)).position


def step_agent_by_role(
    sim: GridSim,
    agent: SquadAgent,
    role: RoleEnum | str,
    objective: tuple[float, float],
    step: float = 0.2,
) -> None:
    role_enum = role if isinstance(role, RoleEnum) else RoleEnum(role)
    guard_pos = nearest_guard(sim, agent)

    match role_enum:
        case RoleEnum.FLANK:
            if guard_pos is not None:
                # Arc around the guard: move perpendicular to guard→objective line.
                mid = (
                    (guard_pos[0] + objective[0]) / 2,
                    (guard_pos[1] + objective[1]) / 2,
                )
                flank_target = (
                    mid[0] + (agent.position[1] - mid[1]),
                    mid[1] - (agent.position[0] - mid[0]),
                )
                agent.position = move_toward(agent.position, flank_target, step)
            else:
                agent.position = move_toward(agent.position, objective, step * 0.8)
        case RoleEnum.DISTRACT:
            if guard_pos is not None:
                agent.position = move_toward(agent.position, guard_pos, step * 1.2)
            else:
                agent.position = move_toward(agent.position, objective, step * 0.5)
        case RoleEnum.STEALTH_COVER:
            if guard_pos is not None:
                agent.position = move_away(agent.position, guard_pos, step * 0.6)
            else:
                agent.position = move_toward(agent.position, objective, step * 0.4)
        case RoleEnum.OVERWATCH:
            if guard_pos is not None:
                hold = (
                    agent.position[0] + (agent.position[0] - guard_pos[0]) * 0.1,
                    agent.position[1] + (agent.position[1] - guard_pos[1]) * 0.1,
                )
                agent.position = move_toward(agent.position, hold, step * 0.5)
            else:
                agent.position = move_toward(agent.position, objective, step * 0.3)
        case RoleEnum.BREACH:
            agent.position = move_toward(agent.position, objective, step * 1.1)
