import pytest

from contracts import PerceptionFrame
from engine.negotiation import ReflexNegotiator


def _frame(agent_id: str, tick: int, *, cooldown: int = 0) -> PerceptionFrame:
    return PerceptionFrame(
        agent_id=agent_id,
        tick=tick,
        position=(1.0, 2.0),
        heading=0.0,
        visibility_polygon=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)],
        cooldown_ticks=cooldown,
    )


@pytest.mark.asyncio
async def test_role_cooldown_skips_bidding_when_calm() -> None:
    negotiator = ReflexNegotiator(squad_id="s1", agent_ids=["a1", "a2"], role_cooldown_ticks=3)
    first = await negotiator.negotiate([_frame("a1", 1), _frame("a2", 1)], "obj", tick=1)
    awarded = {a.agent_id for a in first.directive.awards}

    second = await negotiator.negotiate([_frame("a1", 2), _frame("a2", 2)], "obj", tick=2)
    assert len(second.directive.awards) < len(awarded)


@pytest.mark.asyncio
async def test_role_cooldown_cleared_on_interrupt() -> None:
    negotiator = ReflexNegotiator(squad_id="s1", agent_ids=["a1", "a2"], role_cooldown_ticks=3)
    await negotiator.negotiate([_frame("a1", 1), _frame("a2", 1)], "obj", tick=1)
    calm = await negotiator.negotiate([_frame("a1", 2), _frame("a2", 2)], "obj", tick=2)
    assert len(calm.directive.awards) < 2

    replan = await negotiator.negotiate(
        [_frame("a1", 3), _frame("a2", 3)], "obj", tick=3, interrupted=True
    )
    assert len(replan.directive.awards) == 2


@pytest.mark.asyncio
async def test_perception_cooldown_ticks_forfeits_bid() -> None:
    negotiator = ReflexNegotiator(squad_id="s1", agent_ids=["a1"])
    result = await negotiator.negotiate([_frame("a1", 1, cooldown=2)], "obj", tick=1)
    assert result.forfeited_agents == ["a1"]
    assert result.directive.awards == []
