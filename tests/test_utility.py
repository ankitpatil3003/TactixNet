
from agents.perception import AgentPerception
from agents.utility import utility_for_role
from contracts import AlertLevel, PerceptionFrame, RoleEnum


def test_flank_utility_high_when_calm() -> None:
    frame = PerceptionFrame(
        agent_id="a1",
        tick=1,
        position=(0, 0),
        heading=0,
        visibility_polygon=[],
        alert_level=AlertLevel.CALM,
    )
    perception = AgentPerception(frame)
    assert utility_for_role(perception, RoleEnum.FLANK) > 0.5


def test_distract_utility_high_when_compromised() -> None:
    frame = PerceptionFrame(
        agent_id="a1",
        tick=1,
        position=(0, 0),
        heading=0,
        visibility_polygon=[],
        alert_level=AlertLevel.COMPROMISED,
    )
    perception = AgentPerception(frame)
    assert utility_for_role(perception, RoleEnum.DISTRACT) > utility_for_role(
        perception, RoleEnum.BREACH
    )
