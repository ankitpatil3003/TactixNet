"""Distributed engine mode: Redis pub/sub hot path."""

from __future__ import annotations

import asyncio
import json
import os
import time

import pytest

from contracts import AlertLevel, PerceptionFrame
from engine.bus import MessageBus, parse_squad_channel, squad_channel
from engine.worker import EngineWorker

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
AGENT_IDS = ["a1", "a2", "a3", "a4", "a5"]


def test_parse_squad_channel() -> None:
    assert parse_squad_channel("squad:abc-123:perception") == ("abc-123", "perception")
    assert parse_squad_channel("squad:abc:control") == ("abc", "control")
    assert parse_squad_channel("invalid") is None


@pytest.mark.asyncio
async def test_engine_worker_round_trip() -> None:
    worker_bus = MessageBus(REDIS_URL)
    client_bus = MessageBus(REDIS_URL)
    listener_bus = MessageBus(REDIS_URL)
    try:
        await worker_bus.connect()
        await client_bus.connect()
        await listener_bus.connect()
    except Exception as exc:
        pytest.skip(f"Redis unavailable: {exc}")

    squad_id = "distributed-test-1"
    worker = EngineWorker(worker_bus)
    worker_task = asyncio.create_task(worker.run())
    pubsub = await listener_bus.subscribe(squad_id, "directives")

    try:
        await client_bus.publish_control(
            squad_id,
            {
                "type": "register",
                "agent_ids": AGENT_IDS,
                "objective_ref": "breach-alpha",
            },
        )
        await asyncio.sleep(0.15)

        frame_kwargs = {
            "tick": 1,
            "position": (1.0, 1.0),
            "heading": 0.0,
            "visibility_polygon": [(0, 0), (1, 0), (1, 1)],
            "alert_level": AlertLevel.CALM,
        }
        for agent_id in AGENT_IDS:
            await client_bus.publish_perception(
                squad_id,
                PerceptionFrame(agent_id=agent_id, **frame_kwargs),
            )

        received_channel = ""
        received_payload = ""
        deadline = time.monotonic() + 5.0
        async for channel, data in listener_bus.listen(pubsub):
            received_channel = channel
            received_payload = data
            break
            if time.monotonic() > deadline:
                break

        assert received_payload, "expected directive envelope from engine worker"
        message = json.loads(received_payload)
        assert message["type"] == "directive"
        assert squad_channel(squad_id, "directives") in received_channel
    finally:
        worker_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await worker_task
        await worker_bus.close()
        await client_bus.close()
        await listener_bus.close()
