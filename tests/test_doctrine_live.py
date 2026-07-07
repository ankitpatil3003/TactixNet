"""Tests for live doctrine application and async strategy layer."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from contracts import AlertLevel, RoleEnum
from gateway.app import app
from gateway.live import LiveNegotiationRunner

client = TestClient(app)

AGENT_IDS = [f"a{i}" for i in range(1, 6)]


def _frame(agent_id: str, tick: int, alert: str = AlertLevel.CALM.value) -> str:
    return json.dumps(
        {
            "agent_id": agent_id,
            "tick": tick,
            "position": [float(agent_id[-1]), 2.0],
            "heading": 0.0,
            "visibility_polygon": [[0, 0], [1, 0], [1, 1], [0, 1]],
            "alert_level": alert,
        }
    )


def test_post_doctrine_applies_weights_to_subsequent_directives() -> None:
    create = client.post("/squads", json={"agent_ids": AGENT_IDS})
    squad_id = create.json()["squad_id"]

    doctrine = {
        "squad_id": squad_id,
        "role_weights": {
            RoleEnum.DISTRACT.value: 5.0,
            RoleEnum.FLANK.value: 0.1,
            RoleEnum.STEALTH_COVER.value: 0.1,
            RoleEnum.OVERWATCH.value: 0.1,
            RoleEnum.BREACH.value: 0.1,
        },
        "priority_objective": "breach-gate",
    }
    response = client.post(f"/squads/{squad_id}/doctrine", json=doctrine)
    assert response.status_code == 200

    with client.websocket_connect(f"/ws/squads/{squad_id}") as ws:
        ws.send_text(_frame("a1", tick=1, alert=AlertLevel.COMPROMISED.value))
        for agent_id in AGENT_IDS[1:]:
            ws.send_text(_frame(agent_id, tick=1))
        message = ws.receive_json()

    awards = {a["agent_id"]: a["role"] for a in message["directive"]["awards"]}
    assert awards["a1"] == RoleEnum.DISTRACT.value


@pytest.mark.asyncio
async def test_strategy_refresh_does_not_block_reflex_loop() -> None:
    runner = LiveNegotiationRunner(squad_id="strategy-test", agent_ids=["a1"])
    applied: list[str] = []

    async def slow_apply(doctrine) -> None:
        applied.append(doctrine.priority_objective)

    with patch.object(
        runner._strategy,
        "generate_doctrine",
        new=AsyncMock(side_effect=Exception("LLM down")),
    ):
        runner.schedule_strategy_refresh(
            tick=100,
            context="test",
            after_replan=True,
            on_applied=slow_apply,
        )
        with pytest.raises(Exception, match="LLM down"):
            await runner._strategy_task

    frame = json.loads(_frame("a1", tick=1))
    from contracts import PerceptionFrame

    results = await runner.ingest_frame(PerceptionFrame.model_validate(frame))
    assert len(results) == 1


@pytest.mark.asyncio
async def test_recovery_ms_reported_on_interrupt() -> None:
    runner = LiveNegotiationRunner(squad_id="recovery-test", agent_ids=AGENT_IDS)
    from contracts import PerceptionFrame

    alert_frame = PerceptionFrame.model_validate(
        json.loads(_frame("a1", tick=1, alert=AlertLevel.ALERT.value))
    )
    calm_frames = [
        PerceptionFrame.model_validate(json.loads(_frame(aid, tick=1)))
        for aid in AGENT_IDS[1:]
    ]
    await runner.ingest_frame(alert_frame)
    results = []
    for frame in calm_frames:
        results.extend(await runner.ingest_frame(frame))

    interrupted = [r for r in results if r.interrupted]
    assert interrupted
    assert interrupted[0].recovery_ms is not None
    assert interrupted[0].recovery_ms >= 0
