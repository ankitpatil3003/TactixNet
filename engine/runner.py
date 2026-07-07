"""Engine runner: subscribes to Redis and orchestrates squad negotiation."""

from __future__ import annotations

import asyncio
import logging
import os

from langgraph.checkpoint.memory import MemorySaver

from contracts import PerceptionFrame
from engine.bus import MessageBus
from engine.graph import build_negotiation_graph
from engine.negotiation import ReflexNegotiator

logging.basicConfig(level=os.environ.get("ENGINE_LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


async def run_squad_cycle(
    bus: MessageBus,
    squad_id: str,
    agent_ids: list[str],
    frames: list[PerceptionFrame],
    tick: int,
    objective_ref: str = "default",
) -> None:
    negotiator = ReflexNegotiator(squad_id=squad_id, agent_ids=agent_ids)
    graph = build_negotiation_graph(negotiator)
    compiled = graph.compile(checkpointer=MemorySaver())

    config = {"configurable": {"thread_id": squad_id}}
    state = {
        "squad_id": squad_id,
        "tick": tick,
        "objective_ref": objective_ref,
        "frames": [f.model_dump() for f in frames],
        "replan_count": 0,
    }
    result = await compiled.ainvoke(state, config)
    directive_data = result.get("directive")
    if directive_data:
        from contracts import SquadDirective

        directive = SquadDirective.model_validate(directive_data)
        await bus.publish_directive(squad_id, directive)


async def main() -> None:
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    bus = MessageBus(redis_url)
    await bus.connect()
    logger.info("TactixNet engine runner started")

    try:
        while True:
            await asyncio.sleep(1)
    finally:
        await bus.close()


if __name__ == "__main__":
    asyncio.run(main())
