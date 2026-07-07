import json

import pytest
from fastapi.testclient import TestClient

from gateway.app import app

client = TestClient(app)


def test_events_endpoint_returns_list_for_squad() -> None:
    create = client.post("/squads", json={"agent_ids": ["a1", "a2"]})
    squad_id = create.json()["squad_id"]

    response = client.get(f"/squads/{squad_id}/events")
    assert response.status_code == 200
    body = response.json()
    assert body["squad_id"] == squad_id
    assert isinstance(body["events"], list)


def test_events_logged_after_websocket_activity() -> None:
    create = client.post("/squads", json={"agent_ids": ["a1"]})
    squad_id = create.json()["squad_id"]

    frame = {
        "agent_id": "a1",
        "tick": 1,
        "position": [1.0, 2.0],
        "heading": 0.0,
        "visibility_polygon": [[0, 0], [1, 0], [1, 1]],
        "alert_level": "CALM",
    }
    with client.websocket_connect(f"/ws/squads/{squad_id}") as ws:
        ws.send_text(json.dumps(frame))
        ws.receive_json()

    events = client.get(f"/squads/{squad_id}/events").json()["events"]
    types = {e["type"] for e in events}
    assert "perception" in types
    assert "directive" in types


@pytest.mark.asyncio
async def test_event_logger_memory_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    from gateway.events import SquadEventLogger

    async def fail_connect(self) -> None:
        self._bus = None

    monkeypatch.setattr(SquadEventLogger, "connect", fail_connect)
    logger = SquadEventLogger()
    await logger.connect()
    assert logger.available is False
    await logger.log("squad-x", "test", {"ok": True})
    events = await logger.read("squad-x")
    assert len(events) == 1
    assert events[0]["type"] == "test"
