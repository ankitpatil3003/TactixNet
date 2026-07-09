"""Distributed engine worker: consumes Redis perception/control, publishes directives."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from contracts import DoctrineUpdate, PerceptionFrame
from engine.bus import MessageBus, parse_squad_channel
from engine.live import CycleResult, LiveNegotiationRunner

logger = logging.getLogger(__name__)


class EngineWorker:
    """Runs per-squad negotiation from Redis pub/sub messages."""

    def __init__(self, bus: MessageBus, *, checkpoint_bus: MessageBus | None = None) -> None:
        self._bus = bus
        self._checkpoint_bus = checkpoint_bus
        self._runners: dict[str, LiveNegotiationRunner] = {}

    def register_squad(
        self,
        squad_id: str,
        agent_ids: list[str],
        *,
        objective_ref: str = "breach-alpha",
    ) -> LiveNegotiationRunner:
        runner = LiveNegotiationRunner(
            squad_id=squad_id,
            agent_ids=agent_ids,
            objective_ref=objective_ref,
            checkpoint_bus=self._checkpoint_bus,
        )
        self._runners[squad_id] = runner
        logger.info("Registered squad %s (%d agents)", squad_id[:8], len(agent_ids))
        return runner

    def get_runner(self, squad_id: str) -> LiveNegotiationRunner | None:
        return self._runners.get(squad_id)

    async def handle_control(self, squad_id: str, payload: dict[str, Any]) -> None:
        msg_type = payload.get("type")
        if msg_type == "register":
            agent_ids = payload.get("agent_ids", [])
            objective_ref = payload.get("objective_ref", "breach-alpha")
            if not agent_ids:
                return
            runner = self.register_squad(
                squad_id, list(agent_ids), objective_ref=str(objective_ref)
            )
            doctrine_raw = payload.get("doctrine")
            if doctrine_raw:
                doctrine = DoctrineUpdate.model_validate(doctrine_raw)
                runner.apply_doctrine(doctrine)
            return

        runner = self._runners.get(squad_id)
        if runner is None:
            return

        if msg_type == "doctrine":
            doctrine = DoctrineUpdate.model_validate(payload["doctrine"])
            runner.apply_doctrine(doctrine)
            await self._bus.publish_doctrine_update(
                squad_id,
                {
                    "type": "doctrine",
                    "source": payload.get("source", "control"),
                    "doctrine": doctrine.model_dump(mode="json"),
                },
            )

    async def handle_perception(self, squad_id: str, frame: PerceptionFrame) -> None:
        runner = self._runners.get(squad_id)
        if runner is None:
            runner = self.register_squad(squad_id, [frame.agent_id])
        results = await runner.ingest_frame(frame)
        await self._publish_cycle_results(squad_id, frame, results)

    async def _publish_cycle_results(
        self,
        squad_id: str,
        frame: PerceptionFrame,
        results: list[CycleResult],
    ) -> None:
        runner = self._runners.get(squad_id)
        if runner is None:
            return

        for result in results:
            await self._bus.publish_directive_envelope(squad_id, result.to_message())
            if result.interrupted:
                await self._bus.publish_control(
                    squad_id,
                    {
                        "type": "interrupt",
                        "tick": frame.tick,
                        "recovery_ms": result.recovery_ms,
                        "replan_count": result.replan_count,
                    },
                )

        if not results:
            return

        last = results[-1]
        context = (
            f"tick={frame.tick} interrupted={last.interrupted} "
            f"replans={last.replan_count} objective={last.objective_ref}"
        )

        async def on_doctrine_applied(doctrine: DoctrineUpdate) -> None:
            await self._bus.publish_doctrine_update(
                squad_id,
                {
                    "type": "doctrine",
                    "source": "strategy",
                    "doctrine": doctrine.model_dump(mode="json"),
                },
            )

        runner.schedule_strategy_refresh(
            tick=frame.tick,
            context=context,
            after_replan=last.interrupted,
            on_applied=on_doctrine_applied,
        )

    async def run(self) -> None:
        pubsub = await self._bus.psubscribe(
            "squad:*:perception",
            "squad:*:control",
        )
        logger.info("Engine worker listening on squad:*:perception and squad:*:control")
        async for message in pubsub.listen():
            if message["type"] != "pmessage":
                continue
            channel = str(message["channel"])
            data = str(message["data"])
            parsed = parse_squad_channel(channel)
            if parsed is None:
                continue
            squad_id, suffix = parsed
            try:
                if suffix == "control":
                    await self.handle_control(squad_id, json.loads(data))
                elif suffix == "perception":
                    frame = PerceptionFrame.model_validate_json(data)
                    await self.handle_perception(squad_id, frame)
            except Exception:
                logger.exception("Failed to process %s for squad %s", suffix, squad_id[:8])


def engine_mode() -> str:
    return os.environ.get("ENGINE_MODE", "inprocess").lower()


def is_distributed_mode() -> bool:
    return engine_mode() == "distributed"
