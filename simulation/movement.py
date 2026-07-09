"""Role-based agent movement helpers for the living simulation."""

from __future__ import annotations

import math

from contracts import AlertLevel, RoleEnum, alert_level_rank
from simulation.bounds import clamp_position
from simulation.grid import GridSim, SquadAgent, _distance, _step_toward


def move_toward(
    position: tuple[float, float], target: tuple[float, float], step: float
) -> tuple[float, float]:
    return _step_toward(position, target, step)


def move_away(
    position: tuple[float, float],
    threat: tuple[float, float],
    step: float,
    *,
    objective: tuple[float, float] | None = None,
    bounds: tuple[float, float] | None = None,
) -> tuple[float, float]:
    dx = position[0] - threat[0]
    dy = position[1] - threat[1]
    dist = math.hypot(dx, dy)
    if dist < 1e-6:
        fled = (position[0] + step, position[1])
    else:
        fled = (position[0] + dx / dist * step, position[1] + dy / dist * step)

    if bounds is not None:
        width, height = bounds
        clamped = clamp_position(fled, width, height)
        if objective is not None and _distance(clamped, fled) < 1e-4:
            return move_toward(position, objective, step * 0.5)
        return clamped
    return fled


def nearest_guard(sim: GridSim, agent: SquadAgent) -> tuple[float, float] | None:
    if not sim.guards:
        return None
    return min(sim.guards, key=lambda g: _distance(agent.position, g.position)).position


def squad_centroid(sim: GridSim) -> tuple[float, float]:
    if not sim.agents:
        return (0.0, 0.0)
    xs = [a.position[0] for a in sim.agents]
    ys = [a.position[1] for a in sim.agents]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def _set_agent_position(
    agent: SquadAgent,
    new_pos: tuple[float, float],
    sim: GridSim,
) -> None:
    old = agent.position
    agent.position = clamp_position(new_pos, sim.width, sim.height)
    dx = agent.position[0] - old[0]
    dy = agent.position[1] - old[1]
    if math.hypot(dx, dy) > 1e-6:
        agent.heading = math.degrees(math.atan2(dy, dx))


def _perpendicular_point(
    origin: tuple[float, float],
    line_start: tuple[float, float],
    line_end: tuple[float, float],
    side: float = 1.0,
) -> tuple[float, float]:
    dx = line_end[0] - line_start[0]
    dy = line_end[1] - line_start[1]
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return origin
    perp_x = -dy / length * side
    perp_y = dx / length * side
    return (origin[0] + perp_x * 2.0, origin[1] + perp_y * 2.0)


def step_agent_by_role(
    sim: GridSim,
    agent: SquadAgent,
    role: RoleEnum | str,
    objective: tuple[float, float],
    step: float = 0.2,
    *,
    alert_level: AlertLevel = AlertLevel.CALM,
) -> None:
    role_enum = role if isinstance(role, RoleEnum) else RoleEnum(role)
    guard_pos = nearest_guard(sim, agent)
    under_pressure = alert_level_rank(alert_level) >= alert_level_rank(AlertLevel.ALERT)
    centroid = squad_centroid(sim)
    bounds = (float(sim.width), float(sim.height))

    match role_enum:
        case RoleEnum.FLANK:
            if guard_pos is not None:
                side = 1.0 if agent.position[0] < centroid[0] else -1.0
                flank_target = _perpendicular_point(
                    agent.position, guard_pos, objective, side=side
                )
                flank_target = (
                    flank_target[0] * 0.4 + objective[0] * 0.6,
                    flank_target[1] * 0.4 + objective[1] * 0.6,
                )
                move_step = step * 0.7 if under_pressure else step
                _set_agent_position(
                    agent, move_toward(agent.position, flank_target, move_step), sim
                )
            else:
                _set_agent_position(agent, move_toward(agent.position, objective, step * 0.8), sim)
        case RoleEnum.DISTRACT:
            if guard_pos is not None:
                desired_dist = 3.5 * 0.8
                current_dist = _distance(agent.position, guard_pos)
                if current_dist > desired_dist:
                    target = guard_pos
                    move_step = step * 0.8
                else:
                    angle = math.atan2(
                        agent.position[1] - guard_pos[1],
                        agent.position[0] - guard_pos[0],
                    )
                    target = (
                        guard_pos[0] + math.cos(angle) * desired_dist,
                        guard_pos[1] + math.sin(angle) * desired_dist,
                    )
                    move_step = step * 0.5
                _set_agent_position(agent, move_toward(agent.position, target, move_step), sim)
            else:
                _set_agent_position(agent, move_toward(agent.position, objective, step * 0.5), sim)
        case RoleEnum.STEALTH_COVER:
            if guard_pos is not None:
                cover = (
                    (centroid[0] + guard_pos[0]) / 2,
                    (centroid[1] + guard_pos[1]) / 2,
                )
                if under_pressure:
                    new_pos = move_away(
                        agent.position,
                        guard_pos,
                        step * 0.8,
                        objective=objective,
                        bounds=bounds,
                    )
                else:
                    new_pos = move_toward(agent.position, cover, step * 0.5)
                    new_pos = move_toward(new_pos, objective, step * 0.3)
                _set_agent_position(agent, new_pos, sim)
            else:
                _set_agent_position(agent, move_toward(agent.position, objective, step * 0.4), sim)
        case RoleEnum.OVERWATCH:
            if guard_pos is not None:
                retreat = move_away(
                    agent.position,
                    guard_pos,
                    step * 0.5,
                    objective=objective,
                    bounds=bounds,
                )
                hold = move_toward(retreat, objective, step * 0.2)
                _set_agent_position(agent, hold, sim)
            else:
                _set_agent_position(agent, move_toward(agent.position, objective, step * 0.3), sim)
        case RoleEnum.BREACH:
            breach_step = step * 0.5 if under_pressure else step * 1.0
            _set_agent_position(agent, move_toward(agent.position, objective, breach_step), sim)
