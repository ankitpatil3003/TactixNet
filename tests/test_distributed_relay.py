"""Gateway DirectiveRelay round-trip in distributed mode."""

from __future__ import annotations

import asyncio
import os
import time

import pytest

from contracts import AlertLevel, PerceptionFrame
from engine.bus import MessageBus
from engine.worker import EngineWorker
from gateway.relay import DirectiveRelay
from gateway.sessions import SessionStore

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
AGENT_IDS = ["relay-a1", "relay-a2", "relay-a3", "relay-a4", "relay-a5"]


@pytest.mark.asyncio
async def test_directive_relay_engine_round_trip() -> None:
    worker_bus = MessageBus(REDIS_URL)
    relay_bus = MessageBus(REDIS_URL)
    try:
        await worker_bus.connect()
        await relay_bus.connect()
    except Exception as exc:
        pytest.skip(f"Redis unavailable: {exc}")

    store = SessionStore()
    session = store.create("relay-squad-1", AGENT_IDS, distributed=True)
    broadcast_messages: list[dict] = []

    async def on_persist(_session) -> None:
        return None

    async def on_broadcast(_session, message: dict) -> None:
        broadcast_messages.append(message)

    async def on_event(_squad_id: str, _kind: str, _payload: dict) -> None:
        return None

    relay = DirectiveRelay(
        relay_bus,
        store,
        on_persist=on_persist,
        on_broadcast=on_broadcast,
        on_event=on_event,
    )
    worker = EngineWorker(worker_bus)
    worker_task = asyncio.create_task(worker.run())
    relay_task = asyncio.create_task(relay.run())

    try:
        await relay.register_squad(session)
        await asyncio.sleep(0.15)

        frame_kwargs = {
            "tick": 1,
            "position": (1.0, 1.0),
            "heading": 0.0,
            "visibility_polygon": [(0, 0), (1, 0), (1, 1)],
            "alert_level": AlertLevel.CALM,
        }
        for agent_id in AGENT_IDS:
            await worker_bus.publish_perception(
                squad_id=session.squad_id,
                frame=PerceptionFrame(agent_id=agent_id, **frame_kwargs),
            )

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if any(m.get("type") == "directive" for m in broadcast_messages):
                break
            await asyncio.sleep(0.05)

        directive_messages = [m for m in broadcast_messages if m.get("type") == "directive"]
        assert directive_messages, "relay should fan out engine directive to gateway sockets"
        assert directive_messages[0]["directive"]["tick"] == 1
    finally:
        relay_task.cancel()
        worker_task.cancel()
        for task in (relay_task, worker_task):
            with pytest.raises(asyncio.CancelledError):
                await task
        await worker_bus.close()
        await relay_bus.close()


@pytest.mark.asyncio
async def test_health_reports_engine_worker_when_heartbeat_present() -> None:
    from engine.heartbeat import pulse

    bus = MessageBus(REDIS_URL)
    try:
        await bus.connect()
    except Exception as exc:
        pytest.skip(f"Redis unavailable: {exc}")

    try:
        await pulse(bus)
        from engine.heartbeat import engine_worker_status

        assert await engine_worker_status(bus) == "connected"
    finally:
        await bus.client.delete("tactixnet:engine:heartbeat")
        await bus.close()
