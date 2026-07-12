"""Engine runner: distributed worker subscribing to Redis pub/sub."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os

from engine.bus import MessageBus
from engine.heartbeat import pulse, run_heartbeat_loop
from engine.worker import EngineWorker

logging.basicConfig(level=os.environ.get("ENGINE_LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


async def main() -> None:
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    bus = MessageBus(redis_url)
    await bus.connect()
    await pulse(bus)

    checkpoint_bus: MessageBus | None = None
    if os.environ.get("USE_REDIS_CHECKPOINT") == "1":
        checkpoint_bus = MessageBus(redis_url)
        await checkpoint_bus.connect()

    worker = EngineWorker(bus, checkpoint_bus=checkpoint_bus)
    heartbeat_task = asyncio.create_task(run_heartbeat_loop(bus))
    logger.info("TactixNet engine worker started (ENGINE_MODE=distributed)")
    try:
        await worker.run()
    finally:
        heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task
        if checkpoint_bus is not None:
            await checkpoint_bus.close()
        await bus.close()


if __name__ == "__main__":
    asyncio.run(main())
