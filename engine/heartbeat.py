"""Engine worker liveness via Redis heartbeat."""

from __future__ import annotations

import asyncio
import time

from engine.bus import MessageBus

ENGINE_HEARTBEAT_KEY = "tactixnet:engine:heartbeat"
HEARTBEAT_TTL_SECONDS = 30
HEARTBEAT_INTERVAL_SECONDS = 10.0


async def pulse(bus: MessageBus) -> None:
    await bus.client.set(
        ENGINE_HEARTBEAT_KEY,
        str(time.time()),
        ex=HEARTBEAT_TTL_SECONDS,
    )


async def run_heartbeat_loop(
    bus: MessageBus,
    *,
    interval: float = HEARTBEAT_INTERVAL_SECONDS,
) -> None:
    while True:
        await pulse(bus)
        await asyncio.sleep(interval)


async def engine_worker_status(bus: MessageBus) -> str:
    raw = await bus.client.get(ENGINE_HEARTBEAT_KEY)
    if raw is None:
        return "offline"
    try:
        age = time.time() - float(raw)
    except ValueError:
        return "offline"
    if age > HEARTBEAT_TTL_SECONDS:
        return "stale"
    return "connected"
