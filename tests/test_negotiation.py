import pytest

from contracts import AlertLevel, PerceptionFrame, RoleEnum
from engine.negotiation import ReflexNegotiator


def _frame(agent_id: str, alert: AlertLevel = AlertLevel.CALM, ammo: int = 30) -> PerceptionFrame:
    return PerceptionFrame(
        agent_id=agent_id,
        tick=1,
        position=(float(agent_id[-1]), 0.0),
        heading=0.0,
        visibility_polygon=[(0, 0), (1, 0), (1, 1), (0, 1)],
        alert_level=alert,
        ammo=ammo,
    )


@pytest.mark.asyncio
async def test_five_agent_squad_self_assigns_roles() -> None:
    agent_ids = [f"a{i}" for i in range(1, 6)]
    negotiator = ReflexNegotiator(squad_id="squad-1", agent_ids=agent_ids)
    frames = [_frame(aid) for aid in agent_ids]

    result = await negotiator.negotiate(frames, objective_ref="breach-alpha", tick=10)

    assert result.directive.directive_seq == 1
    assert len(result.directive.awards) == 5
    awarded_agents = {a.agent_id for a in result.directive.awards}
    assert len(awarded_agents) == 5
    awarded_roles = {a.role for a in result.directive.awards}
    assert len(awarded_roles) == 5


@pytest.mark.asyncio
async def test_compromised_agent_prefers_distract() -> None:
    negotiator = ReflexNegotiator(squad_id="squad-2", agent_ids=["a1"])
    frame = _frame("a1", alert=AlertLevel.COMPROMISED)
    result = await negotiator.negotiate([frame], objective_ref="obj", tick=1)
    assert len(result.directive.awards) == 1
    assert result.directive.awards[0].role in RoleEnum


@pytest.mark.asyncio
async def test_slow_agent_forfeits_bid() -> None:
    negotiator = ReflexNegotiator(squad_id="squad-3", agent_ids=["a1", "a2"], bid_timeout_s=0.001)
    frames = [_frame("a1"), _frame("a2")]
    result = await negotiator.negotiate(frames, objective_ref="obj", tick=1)
    assert len(result.directive.awards) >= 1
