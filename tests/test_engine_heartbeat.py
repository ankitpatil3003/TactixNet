"""Engine heartbeat and distributed health reporting."""

from __future__ import annotations

import asyncio
import os
import time

import pytest

from engine.bus import MessageBus
from engine.heartbeat import (
    ENGINE_HEARTBEAT_KEY,
    engine_worker_status,
    pulse,
    run_heartbeat_loop,
)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


@pytest.mark.asyncio
async def test_engine_heartbeat_pulse_and_status() -> None:
    bus = MessageBus(REDIS_URL)
    try:
        await bus.connect()
    except Exception as exc:
        pytest.skip(f"Redis unavailable: {exc}")

    try:
        await pulse(bus)
        assert await engine_worker_status(bus) == "connected"
        raw = await bus.client.get(ENGINE_HEARTBEAT_KEY)
        assert raw is not None
        assert time.time() - float(raw) < 5.0
    finally:
        await bus.client.delete(ENGINE_HEARTBEAT_KEY)
        await bus.close()


@pytest.mark.asyncio
async def test_engine_heartbeat_loop_updates_key() -> None:
    bus = MessageBus(REDIS_URL)
    try:
        await bus.connect()
    except Exception as exc:
        pytest.skip(f"Redis unavailable: {exc}")

    task = asyncio.create_task(run_heartbeat_loop(bus, interval=0.05))
    try:
        await asyncio.sleep(0.15)
        assert await engine_worker_status(bus) == "connected"
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await bus.client.delete(ENGINE_HEARTBEAT_KEY)
        await bus.close()
