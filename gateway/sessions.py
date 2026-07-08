"""Squad session store for gateway control plane."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from contracts.events import DoctrineUpdate, PerceptionFrame, SquadDirective
from gateway.live import LiveNegotiationRunner


@dataclass
class SquadSession:
    squad_id: str
    agent_ids: list[str]
    tick: int = 0
    doctrine: DoctrineUpdate | None = None
    last_directive: SquadDirective | None = None
    perception_buffer: list[PerceptionFrame] = field(default_factory=list)
    runner: LiveNegotiationRunner | None = None
    sockets: set[Any] = field(default_factory=set)
    observers: set[Any] = field(default_factory=set)
    objective_ref: str = "breach-alpha"
    scenario: dict[str, Any] | None = None


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, SquadSession] = {}

    def create(
        self,
        squad_id: str,
        agent_ids: list[str],
        *,
        objective_ref: str = "breach-alpha",
        scenario: dict[str, Any] | None = None,
        checkpoint_bus: Any | None = None,
    ) -> SquadSession:
        session = SquadSession(
            squad_id=squad_id,
            agent_ids=agent_ids,
            objective_ref=objective_ref,
            scenario=scenario,
        )
        session.runner = LiveNegotiationRunner(
            squad_id=squad_id,
            agent_ids=agent_ids,
            objective_ref=objective_ref,
            checkpoint_bus=checkpoint_bus,
        )
        self._sessions[squad_id] = session
        return session

    def get(self, squad_id: str) -> SquadSession | None:
        return self._sessions.get(squad_id)

    def register(self, session: SquadSession) -> None:
        self._sessions[session.squad_id] = session

    def delete(self, squad_id: str) -> None:
        self._sessions.pop(squad_id, None)

    def list_ids(self) -> list[str]:
        return list(self._sessions.keys())
