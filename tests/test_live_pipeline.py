"""Integration tests for the live perception-to-directive pipeline."""

import json

from fastapi.testclient import TestClient

from contracts import AlertLevel
from gateway.app import app

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


def _create_squad() -> str:
    response = client.post("/squads", json={"agent_ids": AGENT_IDS})
    return response.json()["squad_id"]


def test_five_agent_tick_produces_directive_with_five_awards() -> None:
    squad_id = _create_squad()

    with client.websocket_connect(f"/ws/squads/{squad_id}") as ws:
        for agent_id in AGENT_IDS:
            ws.send_text(_frame(agent_id, tick=1))
        message = ws.receive_json()

    assert message["type"] == "directive"
    assert message["latency_ms"] < 150.0
    directive = message["directive"]
    assert directive["directive_seq"] == 1
    assert len(directive["awards"]) == 5
    assert {a["agent_id"] for a in directive["awards"]} == set(AGENT_IDS)


def test_directive_seq_monotonic_across_ticks() -> None:
    squad_id = _create_squad()

    with client.websocket_connect(f"/ws/squads/{squad_id}") as ws:
        seqs = []
        for tick in (1, 2, 3):
            for agent_id in AGENT_IDS:
                ws.send_text(_frame(agent_id, tick=tick))
            message = ws.receive_json()
            seqs.append(message["directive"]["directive_seq"])

    assert seqs == sorted(seqs)
    assert len(set(seqs)) == 3


def test_alert_frame_triggers_replan() -> None:
    squad_id = _create_squad()

    with client.websocket_connect(f"/ws/squads/{squad_id}") as ws:
        ws.send_text(_frame("a1", tick=1, alert=AlertLevel.ALERT.value))
        for agent_id in AGENT_IDS[1:]:
            ws.send_text(_frame(agent_id, tick=1))
        message = ws.receive_json()

    assert message["interrupted"] is True
    assert message["replan_count"] >= 1
    assert "-replan-" in message["objective_ref"]


def test_incomplete_tick_flushed_when_newer_tick_arrives() -> None:
    squad_id = _create_squad()

    with client.websocket_connect(f"/ws/squads/{squad_id}") as ws:
        # Only 3 of 5 agents report tick 1 (two slow agents forfeit)
        for agent_id in AGENT_IDS[:3]:
            ws.send_text(_frame(agent_id, tick=1))
        # A tick-2 frame flushes the incomplete tick 1
        ws.send_text(_frame("a1", tick=2))
        message = ws.receive_json()

    assert message["type"] == "directive"
    assert message["directive"]["tick"] == 1
    assert len(message["directive"]["awards"]) == 3


def test_observer_receives_directives_and_snapshots() -> None:
    squad_id = _create_squad()

    with (
        client.websocket_connect(f"/ws/squads/{squad_id}?mode=observer") as observer,
        client.websocket_connect(f"/ws/squads/{squad_id}") as player,
    ):
        snapshot = {"type": "world_snapshot", "tick": 1, "agents": [], "guards": []}
        player.send_text(json.dumps(snapshot))
        received_snapshot = observer.receive_json()
        assert received_snapshot["type"] == "world_snapshot"

        for agent_id in AGENT_IDS:
            player.send_text(_frame(agent_id, tick=1))
        received_directive = observer.receive_json()
        assert received_directive["type"] == "directive"


def test_last_directive_visible_via_rest() -> None:
    squad_id = _create_squad()

    with client.websocket_connect(f"/ws/squads/{squad_id}") as ws:
        for agent_id in AGENT_IDS:
            ws.send_text(_frame(agent_id, tick=7))
        ws.receive_json()

    state = client.get(f"/squads/{squad_id}").json()
    assert state["last_directive"] is not None
    assert state["last_directive"]["tick"] == 7
