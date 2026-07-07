"""Optional Redis event logger for squad sessions."""

from __future__ import annotations

import json
import os
from collections import defaultdict
from typing import Any

from engine.bus import MessageBus


class SquadEventLogger:
    """Logs squad events to Redis Streams; falls back to in-memory when Redis is unavailable."""

    def __init__(self) -> None:
        self._bus: MessageBus | None = None
        self._memory: dict[str, list[dict[str, str]]] = defaultdict(list)

    async def connect(self) -> None:
        try:
            bus = MessageBus(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
            await bus.connect()
            self._bus = bus
        except Exception:
            self._bus = None

    @property
    def available(self) -> bool:
        return self._bus is not None

    async def log(self, squad_id: str, event_type: str, payload: dict[str, Any]) -> None:
        entry = {
            "id": str(len(self._memory[squad_id])),
            "type": event_type,
            "payload": json.dumps(payload),
        }
        self._memory[squad_id].append(entry)
        if self._bus is None:
            return
        try:
            stream_key = f"squad:{squad_id}:events"
            await self._bus.client.xadd(
                stream_key,
                {"type": event_type, "payload": entry["payload"]},
                maxlen=10000,
            )
        except Exception:
            pass

    async def read(self, squad_id: str, count: int = 100) -> list[dict[str, str]]:
        if self._bus is not None:
            try:
                return await self._bus.read_event_log(squad_id, count=count)
            except Exception:
                pass
        entries = self._memory.get(squad_id, [])
        return list(reversed(entries[-count:]))

    async def close(self) -> None:
        if self._bus is not None:
            await self._bus.close()
            self._bus = None
