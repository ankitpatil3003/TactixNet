"""Redis-backed LangGraph checkpointer."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from typing import Any

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)

from engine.bus import MessageBus


class RedisCheckpointSaver(BaseCheckpointSaver):
    """Persist LangGraph checkpoints in Redis hashes."""

    def __init__(self, bus: MessageBus) -> None:
        super().__init__()
        self._bus = bus

    def _key(self, thread_id: str) -> str:
        return f"checkpoint:{thread_id}"

    def get_tuple(self, config: dict[str, Any]) -> CheckpointTuple | None:
        raise NotImplementedError("Use aget_tuple for async")

    def list(
        self,
        config: dict[str, Any] | None,
        *,
        filter: dict[str, Any] | None = None,
        before: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        raise NotImplementedError("Use alist for async")

    def put(
        self,
        config: dict[str, Any],
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict[str, Any],
    ) -> dict[str, Any]:
        raise NotImplementedError("Use aput for async")

    async def aget_tuple(self, config: dict[str, Any]) -> CheckpointTuple | None:
        thread_id = config["configurable"]["thread_id"]
        raw = await self._bus.client.get(self._key(thread_id))
        if raw is None:
            return None
        data = json.loads(raw)
        return CheckpointTuple(
            config=config,
            checkpoint=data["checkpoint"],
            metadata=data.get("metadata", {}),
            parent_config=data.get("parent_config"),
        )

    async def alist(
        self,
        config: dict[str, Any] | None,
        *,
        filter: dict[str, Any] | None = None,
        before: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        if config is None:
            return
        item = await self.aget_tuple(config)
        if item is not None:
            yield item

    async def aput(
        self,
        config: dict[str, Any],
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict[str, Any],
    ) -> dict[str, Any]:
        thread_id = config["configurable"]["thread_id"]
        payload = json.dumps(
            {
                "checkpoint": checkpoint,
                "metadata": metadata,
                "parent_config": None,
            }
        )
        await self._bus.client.set(self._key(thread_id), payload)
        return config

    async def aput_writes(
        self,
        config: dict[str, Any],
        writes: list[tuple[str, Any]],
        task_id: str,
    ) -> None:
        thread_id = config["configurable"]["thread_id"]
        key = f"checkpoint:{thread_id}:writes:{task_id}"
        payload = json.dumps([{"channel": channel, "value": value} for channel, value in writes])
        await self._bus.client.set(key, payload)
