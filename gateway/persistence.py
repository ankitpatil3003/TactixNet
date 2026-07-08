"""Redis-backed squad session metadata persistence."""

from __future__ import annotations

import json
import os
from typing import Any

from engine.bus import MessageBus

SESSION_TTL_SECONDS = 86_400


class SessionPersistence:
    """Persists squad metadata in Redis hashes with TTL."""

    def __init__(self, redis_url: str | None = None) -> None:
        self._redis_url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self._bus: MessageBus | None = None

    async def connect(self) -> None:
        try:
            bus = MessageBus(self._redis_url)
            await bus.connect()
            self._bus = bus
        except Exception:
            self._bus = None

    @property
    def available(self) -> bool:
        return self._bus is not None

    def _meta_key(self, squad_id: str) -> str:
        return f"squad:{squad_id}:meta"

    async def save(self, squad_id: str, data: dict[str, Any]) -> None:
        if self._bus is None:
            return
        payload = json.dumps(data)
        key = self._meta_key(squad_id)
        await self._bus.client.set(key, payload, ex=SESSION_TTL_SECONDS)

    async def load(self, squad_id: str) -> dict[str, Any] | None:
        if self._bus is None:
            return None
        raw = await self._bus.client.get(self._meta_key(squad_id))
        if raw is None:
            return None
        return json.loads(raw)

    async def list_squad_ids(self) -> list[str]:
        if self._bus is None:
            return []
        ids: list[str] = []
        async for key in self._bus.client.scan_iter(match="squad:*:meta"):
            parts = key.split(":")
            if len(parts) >= 2:
                ids.append(parts[1])
        return ids

    async def close(self) -> None:
        if self._bus is not None:
            await self._bus.close()
            self._bus = None
