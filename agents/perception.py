"""Localized perception model for decentralized agents."""

from contracts import AlertLevel, PerceptionFrame, VisibleEntity


class AgentPerception:
    """Wraps a perception frame with query helpers."""

    def __init__(self, frame: PerceptionFrame) -> None:
        self.frame = frame

    @property
    def agent_id(self) -> str:
        return self.frame.agent_id

    @property
    def alert_level(self) -> AlertLevel:
        return self.frame.alert_level

    @property
    def position(self) -> tuple[float, float]:
        return self.frame.position

    def visible_threats(self) -> list[VisibleEntity]:
        return [e for e in self.frame.visible_entities if e.threat_level > 0.3]

    def has_line_of_sight_threat(self) -> bool:
        return len(self.visible_threats()) > 0

    def ammo_ratio(self) -> float:
        return min(self.frame.ammo / 30.0, 1.0)

    def is_compromised(self) -> bool:
        return self.frame.alert_level in (AlertLevel.ALERT, AlertLevel.COMPROMISED)
