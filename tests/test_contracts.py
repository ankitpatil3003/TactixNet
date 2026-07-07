import pytest
from pydantic import ValidationError

from contracts import (
    AlertLevel,
    Bid,
    ErrorCode,
    PerceptionFrame,
    RoleEnum,
    SquadDirective,
    TaskAnnouncement,
)


def test_perception_frame_valid() -> None:
    frame = PerceptionFrame(
        agent_id="a1",
        tick=1,
        position=(0.0, 0.0),
        heading=90.0,
        visibility_polygon=[(0, 0), (1, 0), (1, 1)],
        alert_level=AlertLevel.CALM,
    )
    assert frame.agent_id == "a1"


def test_perception_frame_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        PerceptionFrame.model_validate(
            {
                "agent_id": "a1",
                "tick": 1,
                "position": (0.0, 0.0),
                "heading": 90.0,
                "visibility_polygon": [],
                "extra": "bad",
            }
        )


def test_squad_directive_monotonic_seq() -> None:
    directive = SquadDirective(
        squad_id="s1",
        directive_seq=1,
        tick=10,
        awards=[],
        objective_ref="obj-1",
    )
    assert directive.directive_seq == 1


def test_task_announcement_role_enum() -> None:
    task = TaskAnnouncement(
        task_id="t1",
        role=RoleEnum.FLANK,
        objective_ref="corridor-a",
        deadline_tick=100,
    )
    assert task.role == RoleEnum.FLANK


def test_bid_utility() -> None:
    bid = Bid(agent_id="a1", task_id="t1", utility=0.85)
    assert bid.utility == 0.85


def test_error_code_values() -> None:
    assert ErrorCode.MALFORMED_FRAME.value == "MALFORMED_FRAME"
