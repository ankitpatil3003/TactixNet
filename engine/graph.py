"""LangGraph squad orchestration graph with interrupt replanning."""

from __future__ import annotations

from typing import Literal

from langgraph.graph import END, StateGraph

from contracts import AlertLevel, PerceptionFrame, RoleEnum, alert_level_rank
from engine.negotiation import ReflexNegotiator
from engine.state import SquadState


def build_negotiation_graph(negotiator: ReflexNegotiator) -> StateGraph:
    graph: StateGraph = StateGraph(SquadState)

    graph.add_node("ingest_perception", _ingest_perception)
    graph.add_node("detect_conflict", _detect_conflict)
    graph.add_node("announce_tasks", _announce_tasks)
    graph.add_node("collect_bids", _make_collect_bids(negotiator))
    graph.add_node("award_roles", _award_roles)
    graph.add_node("commit_directive", _commit_directive)
    graph.add_node("compromised_replan", _compromised_replan)

    graph.set_entry_point("ingest_perception")
    graph.add_edge("ingest_perception", "detect_conflict")
    graph.add_conditional_edges(
        "detect_conflict",
        _route_after_conflict,
        {
            "replan": "compromised_replan",
            "continue": "announce_tasks",
        },
    )
    graph.add_edge("compromised_replan", "announce_tasks")
    graph.add_edge("announce_tasks", "collect_bids")
    graph.add_edge("collect_bids", "award_roles")
    graph.add_edge("award_roles", "commit_directive")
    graph.add_edge("commit_directive", END)

    return graph


def _ingest_perception(state: SquadState) -> SquadState:
    return state


def _detect_conflict(state: SquadState) -> SquadState:
    frames = [PerceptionFrame.model_validate(f) for f in state.get("frames", [])]
    max_alert = AlertLevel.CALM
    alert_agent: str | None = None
    for frame in frames:
        if alert_level_rank(frame.alert_level) > alert_level_rank(max_alert):
            max_alert = frame.alert_level
            alert_agent = frame.agent_id

    interrupted = max_alert in (AlertLevel.ALERT, AlertLevel.COMPROMISED)
    return {
        **state,
        "interrupted": interrupted,
        "interrupt_reason": max_alert.value if interrupted else None,
        "alert_agent_id": alert_agent,
    }


def _route_after_conflict(state: SquadState) -> Literal["replan", "continue"]:
    if state.get("interrupted"):
        return "replan"
    return "continue"


def _compromised_replan(state: SquadState) -> SquadState:
    """Replan sub-graph: boost distract/stealth weights after compromise."""
    replan_count = state.get("replan_count", 0) + 1
    return {
        **state,
        "replan_count": replan_count,
        "objective_ref": f"{state.get('objective_ref', 'obj')}-replan-{replan_count}",
    }


def _announce_tasks(state: SquadState) -> SquadState:
    objective = state.get("objective_ref", "default")
    tick = state.get("tick", 0)
    roles = list(RoleEnum)[:5]
    tasks = [
        {
            "task_id": f"{objective}-{role.value}",
            "role": role.value,
            "objective_ref": objective,
            "deadline_tick": tick + 10,
        }
        for role in roles
    ]
    return {**state, "tasks": tasks}


def _make_collect_bids(negotiator: ReflexNegotiator):
    async def collect_bids(state: SquadState) -> SquadState:
        frames = [PerceptionFrame.model_validate(f) for f in state.get("frames", [])]
        if state.get("interrupted"):
            negotiator.update_bidder_weights(
                {RoleEnum.DISTRACT: 1.5, RoleEnum.STEALTH_COVER: 1.3}
            )
        result = await negotiator.negotiate(
            frames,
            objective_ref=state.get("objective_ref", "default"),
            tick=state.get("tick", 0),
            interrupted=bool(state.get("interrupted")),
        )
        return {
            **state,
            "bids": [b.model_dump() for b in result.bids_received],
            "awards": [a.model_dump() for a in result.directive.awards],
            "directive_seq": result.directive.directive_seq,
        }

    return collect_bids


def _award_roles(state: SquadState) -> SquadState:
    return state


def _commit_directive(state: SquadState) -> SquadState:
    directive = {
        "squad_id": state.get("squad_id", ""),
        "directive_seq": state.get("directive_seq", 1),
        "tick": state.get("tick", 0),
        "awards": state.get("awards", []),
        "objective_ref": state.get("objective_ref", "default"),
    }
    return {**state, "directive": directive}
