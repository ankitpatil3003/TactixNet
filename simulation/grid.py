"""Headless grid-based tactics simulation harness."""

from __future__ import annotations

from dataclasses import dataclass, field

from contracts import AlertLevel, PerceptionFrame, VisibleEntity


@dataclass
class Guard:
    guard_id: str
    position: tuple[float, float]
    patrol_route: list[tuple[float, float]]
    vision_range: float = 5.0


@dataclass
class SquadAgent:
    agent_id: str
    position: tuple[float, float]
    heading: float = 0.0
    ammo: int = 30


@dataclass
class GridSim:
    width: int = 20
    height: int = 20
    tick: int = 0
    agents: list[SquadAgent] = field(default_factory=list)
    guards: list[Guard] = field(default_factory=list)

    def advance_tick(self) -> None:
        self.tick += 1
        for guard in self.guards:
            if guard.patrol_route:
                idx = self.tick % len(guard.patrol_route)
                guard.position = guard.patrol_route[idx]

    def perception_for_agent(self, agent: SquadAgent) -> PerceptionFrame:
        visible: list[VisibleEntity] = []
        alert = AlertLevel.CALM
        for guard in self.guards:
            dist = _distance(agent.position, guard.position)
            if dist <= guard.vision_range:
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
                    if alert_level_rank(AlertLevel.ALERT) > alert_level_rank(alert):
                        alert = AlertLevel.ALERT
                elif dist <= guard.vision_range * 0.8:
                    if alert_level_rank(AlertLevel.SUSPICIOUS) > alert_level_rank(alert):
                        alert = AlertLevel.SUSPICIOUS

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
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _vision_cone(pos: tuple[float, float], heading: float) -> list[tuple[float, float]]:
    import math

    x, y = pos
    angle = math.radians(heading)
    return [
        (x, y),
        (x + 5 * math.cos(angle - 0.5), y + 5 * math.sin(angle - 0.5)),
        (x + 5 * math.cos(angle + 0.5), y + 5 * math.sin(angle + 0.5)),
    ]


def alert_level_rank(level: AlertLevel) -> int:
    order = {
        AlertLevel.CALM: 0,
        AlertLevel.SUSPICIOUS: 1,
        AlertLevel.ALERT: 2,
        AlertLevel.COMPROMISED: 3,
    }
    return order[level]
