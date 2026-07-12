"""Redis checkpoint saver write persistence."""

from __future__ import annotations

import json
import os

import pytest

from engine.bus import MessageBus
from engine.checkpoint import RedisCheckpointSaver

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


@pytest.mark.asyncio
async def test_redis_checkpoint_aput_writes() -> None:
    bus = MessageBus(REDIS_URL)
    try:
        await bus.connect()
    except Exception as exc:
        pytest.skip(f"Redis unavailable: {exc}")

    saver = RedisCheckpointSaver(bus)
    config = {"configurable": {"thread_id": "test-thread-writes"}}
    writes = [("messages", [{"role": "user", "content": "ping"}])]
    try:
        await saver.aput_writes(config, writes, task_id="task-1")
        raw = await bus.client.get("checkpoint:test-thread-writes:writes:task-1")
        assert raw is not None
        stored = json.loads(raw)
        assert stored[0]["channel"] == "messages"
        assert stored[0]["value"][0]["content"] == "ping"
    finally:
        await bus.client.delete("checkpoint:test-thread-writes:writes:task-1")
        await bus.close()
