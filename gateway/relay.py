"""Relay Redis directive/doctrine messages to gateway WebSocket clients."""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from contracts import DoctrineUpdate, SquadDirective
from engine.bus import MessageBus, parse_squad_channel
from gateway.sessions import SessionStore, SquadSession

logger = logging.getLogger(__name__)

PersistCallback = Callable[[SquadSession], Awaitable[None]]
BroadcastCallback = Callable[[SquadSession, dict[str, Any]], Awaitable[None]]
EventLogCallback = Callable[[str, str, dict[str, Any]], Awaitable[None]]


class DirectiveRelay:
    """Subscribes to engine-published directives and fans out to squad sockets."""

    def __init__(
        self,
        bus: MessageBus,
        store: SessionStore,
        *,
        on_persist: PersistCallback,
        on_broadcast: BroadcastCallback,
        on_event: EventLogCallback,
    ) -> None:
        self._bus = bus
        self._store = store
        self._on_persist = on_persist
        self._on_broadcast = on_broadcast
        self._on_event = on_event

    async def register_squad(self, session: SquadSession) -> None:
        await self._bus.publish_control(
            session.squad_id,
            {
                "type": "register",
                "agent_ids": session.agent_ids,
                "objective_ref": session.objective_ref,
                "doctrine": (
                    session.doctrine.model_dump(mode="json") if session.doctrine else None
                ),
            },
        )

    async def publish_doctrine(
        self,
        session: SquadSession,
        doctrine: DoctrineUpdate,
        *,
        source: str,
    ) -> None:
        await self._bus.publish_control(
            session.squad_id,
            {
                "type": "doctrine",
                "source": source,
                "doctrine": doctrine.model_dump(mode="json"),
            },
        )

    async def _handle_directive(self, squad_id: str, message: dict[str, Any]) -> None:
        session = self._store.get(squad_id)
        if session is None:
            return
        directive_raw = message.get("directive")
        if directive_raw:
            session.last_directive = SquadDirective.model_validate(directive_raw)
        await self._on_broadcast(session, message)
        await self._on_event(squad_id, "directive", message)
        if message.get("interrupted"):
            await self._on_event(
                squad_id,
                "interrupt",
                {
                    "tick": message.get("directive", {}).get("tick"),
                    "recovery_ms": message.get("recovery_ms"),
                    "replan_count": message.get("replan_count"),
                },
            )
        await self._on_persist(session)

    async def _handle_doctrine(self, squad_id: str, message: dict[str, Any]) -> None:
        session = self._store.get(squad_id)
        if session is None:
            return
        doctrine_raw = message.get("doctrine")
        if doctrine_raw:
            session.doctrine = DoctrineUpdate.model_validate(doctrine_raw)
        await self._on_broadcast(session, message)
        await self._on_event(squad_id, "doctrine", message)
        await self._on_persist(session)

    async def run(self) -> None:
        pubsub = await self._bus.psubscribe("squad:*:directives", "squad:*:doctrine")
        logger.info("Directive relay listening on squad:*:directives and squad:*:doctrine")
        async for message in pubsub.listen():
            if message["type"] != "pmessage":
                continue
            channel = str(message["channel"])
            data = str(message["data"])
            parsed = parse_squad_channel(channel)
            if parsed is None:
                continue
            squad_id, suffix = parsed
            try:
                payload = json.loads(data)
                if suffix == "directives":
                    await self._handle_directive(squad_id, payload)
                elif suffix == "doctrine":
                    await self._handle_doctrine(squad_id, payload)
            except Exception:
                logger.exception("Relay failed for %s on squad %s", suffix, squad_id[:8])
