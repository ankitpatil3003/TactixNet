import os

import pytest

from contracts import AlertLevel, PerceptionFrame, SquadDirective
from engine.bus import MessageBus, squad_channel

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


@pytest.fixture
async def bus() -> MessageBus:
    message_bus = MessageBus(REDIS_URL)
    try:
        await message_bus.connect()
        yield message_bus
    except Exception as exc:
        pytest.skip(f"Redis unavailable: {exc}")
    finally:
        await message_bus.close()


@pytest.mark.asyncio
async def test_publish_perception_and_fanout(bus: MessageBus) -> None:
    squad_id = "test-squad-1"
    pubsub = await bus.subscribe(squad_id, "perception")

    frame = PerceptionFrame(
        agent_id="a1",
        tick=1,
        position=(0.0, 0.0),
        heading=0.0,
        visibility_polygon=[],
        alert_level=AlertLevel.CALM,
    )
    await bus.publish_perception(squad_id, frame)

    received = []
    async for channel, data in bus.listen(pubsub):
        received.append((channel, data))
        if len(received) >= 1:
            break

    assert squad_channel(squad_id, "perception") in received[0][0]
    parsed = PerceptionFrame.model_validate_json(received[0][1])
    assert parsed.agent_id == "a1"


@pytest.mark.asyncio
async def test_agent_state_rehydration(bus: MessageBus) -> None:
    squad_id = "test-squad-2"
    await bus.set_agent_state(squad_id, "a1", {"position": [1.0, 2.0], "ammo": 20})
    await bus.set_agent_state(squad_id, "a2", {"position": [3.0, 4.0], "ammo": 15})

    states = await bus.rehydrate_squad_agents(squad_id, ["a1", "a2"])
    assert states["a1"]["position"] == [1.0, 2.0]
    assert states["a2"]["ammo"] == 15


@pytest.mark.asyncio
async def test_event_log_stream(bus: MessageBus) -> None:
    squad_id = "test-squad-3"
    directive = SquadDirective(
        squad_id=squad_id,
        directive_seq=1,
        tick=5,
        awards=[],
        objective_ref="obj-1",
    )
    await bus.publish_directive(squad_id, directive)

    events = await bus.read_event_log(squad_id, count=10)
    assert len(events) >= 1
    assert events[0]["type"] == "directive"
