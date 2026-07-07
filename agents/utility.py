"""Per-role utility functions for Contract Net Protocol bidding."""

from typing import assert_never

from agents.perception import AgentPerception
from contracts import AlertLevel, RoleEnum

DEFAULT_ROLE_WEIGHTS: dict[RoleEnum, float] = {
    RoleEnum.FLANK: 1.0,
    RoleEnum.DISTRACT: 1.0,
    RoleEnum.STEALTH_COVER: 1.0,
    RoleEnum.OVERWATCH: 1.0,
    RoleEnum.BREACH: 1.0,
}


def utility_for_role(
    perception: AgentPerception,
    role: RoleEnum,
    weights: dict[RoleEnum, float] | None = None,
) -> float:
    """Compute utility score for a role given local perception."""
    w = weights or DEFAULT_ROLE_WEIGHTS
    base_weight = w.get(role, 1.0)

    match role:
        case RoleEnum.FLANK:
            score = _flank_utility(perception)
        case RoleEnum.DISTRACT:
            score = _distract_utility(perception)
        case RoleEnum.STEALTH_COVER:
            score = _stealth_cover_utility(perception)
        case RoleEnum.OVERWATCH:
            score = _overwatch_utility(perception)
        case RoleEnum.BREACH:
            score = _breach_utility(perception)
        case _ as unreachable:
            assert_never(unreachable)

    return max(0.0, min(1.0, score * base_weight))


def _flank_utility(perception: AgentPerception) -> float:
    threats = perception.visible_threats()
    if perception.is_compromised():
        return 0.2
    if not threats:
        return 0.9
    return 0.6 if perception.frame.alert_level == AlertLevel.SUSPICIOUS else 0.4


def _distract_utility(perception: AgentPerception) -> float:
    if perception.is_compromised():
        return 0.85
    if perception.has_line_of_sight_threat():
        return 0.7
    return 0.3


def _stealth_cover_utility(perception: AgentPerception) -> float:
    if perception.frame.alert_level == AlertLevel.CALM:
        return 0.8
    if perception.frame.alert_level == AlertLevel.SUSPICIOUS:
        return 0.6
    return 0.2


def _overwatch_utility(perception: AgentPerception) -> float:
    visibility = len(perception.frame.visibility_polygon)
    los_bonus = 0.3 if perception.has_line_of_sight_threat() else 0.0
    return min(1.0, 0.4 + visibility * 0.05 + los_bonus)


def _breach_utility(perception: AgentPerception) -> float:
    if perception.is_compromised():
        return 0.1
    return 0.5 + perception.ammo_ratio() * 0.4
