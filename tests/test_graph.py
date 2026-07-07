import pytest
from langgraph.checkpoint.memory import MemorySaver

from contracts import AlertLevel, PerceptionFrame
from engine.graph import build_negotiation_graph
from engine.negotiation import ReflexNegotiator


def _frame(agent_id: str, alert: AlertLevel = AlertLevel.CALM) -> dict:
    return PerceptionFrame(
        agent_id=agent_id,
        tick=1,
        position=(0.0, 0.0),
        heading=0.0,
        visibility_polygon=[(0, 0), (1, 0), (1, 1)],
        alert_level=alert,
    ).model_dump()


@pytest.mark.asyncio
async def test_negotiation_graph_completes() -> None:
    agent_ids = [f"a{i}" for i in range(1, 6)]
    negotiator = ReflexNegotiator(squad_id="g-squad", agent_ids=agent_ids)
    graph = build_negotiation_graph(negotiator).compile(checkpointer=MemorySaver())

    result = await graph.ainvoke(
        {
            "squad_id": "g-squad",
            "tick": 10,
            "objective_ref": "obj-1",
            "frames": [_frame(aid) for aid in agent_ids],
            "replan_count": 0,
        },
        {"configurable": {"thread_id": "g-squad"}},
    )

    assert result["directive"] is not None
    assert len(result["directive"]["awards"]) == 5


@pytest.mark.asyncio
async def test_chaos_alert_triggers_replan() -> None:
    agent_ids = [f"a{i}" for i in range(1, 6)]
    negotiator = ReflexNegotiator(squad_id="chaos-squad", agent_ids=agent_ids)
    graph = build_negotiation_graph(negotiator).compile(checkpointer=MemorySaver())

    frames = [_frame("a1", AlertLevel.ALERT)] + [_frame(aid) for aid in agent_ids[1:]]

    result = await graph.ainvoke(
        {
            "squad_id": "chaos-squad",
            "tick": 20,
            "objective_ref": "obj-chaos",
            "frames": frames,
            "replan_count": 0,
        },
        {"configurable": {"thread_id": "chaos-squad"}},
    )

    assert result["interrupted"] is True
    assert result["replan_count"] >= 1
    assert "-replan-" in result["objective_ref"]
    assert result["directive"]["directive_seq"] >= 1
