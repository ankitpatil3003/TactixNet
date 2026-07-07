"""Redis message bus: pub/sub, streams event log, agent state hashes."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from typing import Any

import redis.asyncio as redis

from contracts.events import PerceptionFrame, SquadDirective


def squad_channel(squad_id: str, channel: str) -> str:
    return f"squad:{squad_id}:{channel}"


class MessageBus:
    """Redis-backed message bus for squad coordination."""

    def __init__(self, redis_url: str | None = None) -> None:
        self._redis_url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self._client: redis.Redis | None = None
        self._pubsub: redis.client.PubSub | None = None

    async def connect(self) -> None:
        self._client = redis.from_url(self._redis_url, decode_responses=True)
        await self.client.ping()

    async def close(self) -> None:
        if self._pubsub is not None:
            await self._pubsub.aclose()
        if self._client is not None:
            await self._client.aclose()

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            raise RuntimeError("MessageBus not connected")
        return self._client

    async def publish_perception(self, squad_id: str, frame: PerceptionFrame) -> None:
        channel = squad_channel(squad_id, "perception")
        payload = frame.model_dump_json()
        await self.client.publish(channel, payload)
        await self._log_event(squad_id, "perception", payload)

    async def publish_intent(self, squad_id: str, payload: dict[str, Any]) -> None:
        channel = squad_channel(squad_id, "intents")
        data = json.dumps(payload)
        await self.client.publish(channel, data)
        await self._log_event(squad_id, "intent", data)

    async def publish_directive(self, squad_id: str, directive: SquadDirective) -> None:
        channel = squad_channel(squad_id, "directives")
        payload = directive.model_dump_json()
        await self.client.publish(channel, payload)
        await self._log_event(squad_id, "directive", payload)

    async def subscribe(self, squad_id: str, *channels: str) -> redis.client.PubSub:
        if self._pubsub is not None:
            await self._pubsub.close()
        self._pubsub = self.client.pubsub()
        names = [squad_channel(squad_id, ch) for ch in channels]
        await self._pubsub.subscribe(*names)
        return self._pubsub

    async def listen(self, pubsub: redis.client.PubSub) -> AsyncIterator[tuple[str, str]]:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            channel = str(message["channel"])
            data = str(message["data"])
            yield channel, data

    async def set_agent_state(self, squad_id: str, agent_id: str, state: dict[str, Any]) -> None:
        key = f"squad:{squad_id}:agent:{agent_id}"
        await self.client.hset(key, mapping={k: json.dumps(v) for k, v in state.items()})

    async def get_agent_state(self, squad_id: str, agent_id: str) -> dict[str, Any]:
        key = f"squad:{squad_id}:agent:{agent_id}"
        raw = await self.client.hgetall(key)
        return {k: json.loads(v) for k, v in raw.items()}

    async def rehydrate_squad_agents(
        self, squad_id: str, agent_ids: list[str]
    ) -> dict[str, dict[str, Any]]:
        return {agent_id: await self.get_agent_state(squad_id, agent_id) for agent_id in agent_ids}

    async def _log_event(self, squad_id: str, event_type: str, payload: str) -> None:
        stream_key = f"squad:{squad_id}:events"
        await self.client.xadd(stream_key, {"type": event_type, "payload": payload}, maxlen=10000)

    async def read_event_log(self, squad_id: str, count: int = 100) -> list[dict[str, str]]:
        stream_key = f"squad:{squad_id}:events"
        entries = await self.client.xrevrange(stream_key, count=count)
        return [{"id": entry_id, **fields} for entry_id, fields in entries]
