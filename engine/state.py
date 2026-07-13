"""Squad orchestration state for LangGraph."""

from typing import TypedDict


class SquadState(TypedDict, total=False):
    squad_id: str
    tick: int
    objective_ref: str
    frames: list[dict]
    tasks: list[dict]
    bids: list[dict]
    awards: list[dict]
    directive: dict | None
    directive_seq: int
    interrupted: bool
    interrupt_reason: str | None
    alert_agent_id: str | None
    replan_count: int
    last_doctrine_tick: int
    strategy_context_hint: str
    strategy_refresh_requested: bool
    strategy_context: str
