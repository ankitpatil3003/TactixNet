"""Headless grid-based tactics simulation harness."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from contracts import AlertLevel, PerceptionFrame, VisibleEntity, alert_level_rank
from simulation.bounds import clamp_position


@dataclass
class Guard:
    guard_id: str
    position: tuple[float, float]
    patrol_route: list[tuple[float, float]]
    vision_range: float = 3.5
    vision_angle_deg: float = 120.0
    patrol_speed: float = 0.2
    heading: float = 0.0
    state: str = "patrol"
    patrol_index: int = 0
    last_seen_position: tuple[float, float] | None = None
    chase_target_id: str | None = None


@dataclass
class SquadAgent:
    agent_id: str
    position: tuple[float, float]
    heading: float = 0.0
    ammo: int = 30
    compromise_ticks: int = 0


@dataclass
class GridSim:
    width: int = 20
    height: int = 20
    tick: int = 0
    agents: list[SquadAgent] = field(default_factory=list)
    guards: list[Guard] = field(default_factory=list)
    _compromise_counted: set[str] = field(default_factory=set, init=False)

    def advance_tick(self, step: float = 0.25) -> None:
        self.tick += 1
        self._compromise_counted.clear()
        self._update_guard_ai(step)

    def _clamp_guard(self, guard: Guard) -> None:
        guard.position = clamp_position(guard.position, self.width, self.height)

    def _update_guard_ai(self, step: float) -> None:
        for guard in self.guards:
            visible_agents = [
                agent
                for agent in self.agents
                if _guard_can_see_agent(guard, agent.position)
            ]
            if visible_agents:
                nearest = min(visible_agents, key=lambda a: _distance(a.position, guard.position))
                guard.last_seen_position = nearest.position
                guard.chase_target_id = nearest.agent_id
                dist = _distance(nearest.position, guard.position)
                if dist <= guard.vision_range * 0.55:
                    guard.state = "chase"
                    guard.position = _step_toward(
                        guard.position, nearest.position, step * 0.85
                    )
                    _update_heading(guard, nearest.position)
                else:
                    guard.state = "investigate"
                    guard.position = _step_toward(
                        guard.position, guard.last_seen_position, step * 0.9
                    )
                    _update_heading(guard, guard.last_seen_position)
                self._clamp_guard(guard)
                continue

            if guard.state in ("investigate", "chase") and guard.last_seen_position is not None:
                dist = _distance(guard.position, guard.last_seen_position)
                if dist > step:
                    guard.state = "investigate"
                    guard.position = _step_toward(
                        guard.position, guard.last_seen_position, step
                    )
                    _update_heading(guard, guard.last_seen_position)
                else:
                    guard.state = "patrol"
                    guard.last_seen_position = None
                    guard.chase_target_id = None
                self._clamp_guard(guard)
                continue

            guard.state = "patrol"
            if guard.patrol_route:
                target = guard.patrol_route[guard.patrol_index]
                dist = _distance(guard.position, target)
                if dist <= guard.patrol_speed:
                    guard.patrol_index = (guard.patrol_index + 1) % len(guard.patrol_route)
                    target = guard.patrol_route[guard.patrol_index]
                guard.position = _step_toward(guard.position, target, guard.patrol_speed)
                _update_heading(guard, target)
            self._clamp_guard(guard)

    def perception_for_agent(self, agent: SquadAgent) -> PerceptionFrame:
        visible: list[VisibleEntity] = []
        alert = AlertLevel.CALM
        close_contact = False

        for guard in self.guards:
            dist = _distance(agent.position, guard.position)
            if not _guard_can_see_agent(guard, agent.position):
                continue
            threat = max(0.0, 1.0 - dist / guard.vision_range)
            visible.append(
                VisibleEntity(
                    entity_id=guard.guard_id,
                    entity_type="guard",
                    position=guard.position,
                    threat_level=threat,
                )
            )
            if dist <= guard.vision_range * 0.5:
                close_contact = True
                if alert_level_rank(AlertLevel.ALERT) > alert_level_rank(alert):
                    alert = AlertLevel.ALERT
            elif dist <= guard.vision_range * 0.8:
                if alert_level_rank(AlertLevel.SUSPICIOUS) > alert_level_rank(alert):
                    alert = AlertLevel.SUSPICIOUS

        if close_contact:
            if agent.agent_id not in self._compromise_counted:
                agent.compromise_ticks += 1
                self._compromise_counted.add(agent.agent_id)
        else:
            agent.compromise_ticks = 0

        if agent.compromise_ticks >= 4:
            alert = AlertLevel.COMPROMISED

        return PerceptionFrame(
            agent_id=agent.agent_id,
            tick=self.tick,
            position=agent.position,
            heading=agent.heading,
            visibility_polygon=_vision_cone(agent.position, agent.heading),
            visible_entities=visible,
            alert_level=alert,
            ammo=agent.ammo,
        )

    def all_perceptions(self) -> list[PerceptionFrame]:
        return [self.perception_for_agent(a) for a in self.agents]


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _step_toward(
    position: tuple[float, float], target: tuple[float, float], step: float
) -> tuple[float, float]:
    dx = target[0] - position[0]
    dy = target[1] - position[1]
    dist = _distance(position, target)
    if dist < step:
        return target
    return (position[0] + dx / dist * step, position[1] + dy / dist * step)


def _update_heading(entity: Guard | SquadAgent, target: tuple[float, float]) -> None:
    dx = target[0] - entity.position[0]
    dy = target[1] - entity.position[1]
    if math.hypot(dx, dy) < 1e-6:
        return
    entity.heading = math.degrees(math.atan2(dy, dx))


def _guard_can_see_agent(guard: Guard, agent_pos: tuple[float, float]) -> bool:
    dist = _distance(guard.position, agent_pos)
    if dist > guard.vision_range:
        return False
    if guard.vision_angle_deg >= 359.0:
        return True
    dx = agent_pos[0] - guard.position[0]
    dy = agent_pos[1] - guard.position[1]
    if math.hypot(dx, dy) < 1e-6:
        return True
    angle_to_agent = math.degrees(math.atan2(dy, dx))
    half_arc = guard.vision_angle_deg / 2.0
    delta = _angle_delta(angle_to_agent, guard.heading)
    return abs(delta) <= half_arc


def _angle_delta(a: float, b: float) -> float:
    diff = (a - b + 180.0) % 360.0 - 180.0
    return diff


def _vision_cone(pos: tuple[float, float], heading: float) -> list[tuple[float, float]]:
    x, y = pos
    angle = math.radians(heading)
    return [
        (x, y),
        (x + 5 * math.cos(angle - 0.5), y + 5 * math.sin(angle - 0.5)),
        (x + 5 * math.cos(angle + 0.5), y + 5 * math.sin(angle + 0.5)),
    ]
